"""输入 / 输出校验中间件（constraints）。

输入侧：schema 参数校验，失败返回错误列表拒绝执行；输出侧：把自由文本
解析为结构化指令，解析失败抛 :class:`ConstraintError`，绝不带病执行。

对应接口：doc/03-interfaces/constraints-interface.md §2
"""

from __future__ import annotations

import json
from typing import Any, cast

from .errors import ConstraintError, ConstraintErrorCode
from .middleware import Middleware
from .models import ExecContext, ExecRequest, ExecResponse, ParsedOutput


def _matches_type(value: Any, expected: str) -> bool:  # noqa: PLR0911
    """按 JSON Schema 类型标签校验单个参数值。"""
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True  # 未识别的类型标签不校验


class Validator(Middleware):
    """输入 schema 校验 + 输出结构化解析。"""

    name = "constraints.validator"

    def before(self, ctx: ExecContext, req: ExecRequest) -> ExecRequest:
        errors = self.validate_input(req.tool, req.args, req.schema)
        if errors:
            raise ConstraintError(
                ConstraintErrorCode.OUTPUT_PARSE_FAILED, f"输入校验失败: {errors}"
            )
        return req

    def after(self, ctx: ExecContext, resp: ExecResponse) -> ExecResponse:
        return resp

    def validate_input(self, tool: str, args: dict[str, Any], schema: dict[str, Any]) -> list[str]:
        """输入校验：schema / 类型 / 必填；返回错误列表（空 = 通过）。"""
        errors: list[str] = []
        missing = [k for k in schema.get("required", []) if k not in args]
        if missing:
            errors.append(f"缺少必需参数: {missing}")
        for key, spec in schema.get("properties", {}).items():
            if key not in args:
                continue
            expected = spec.get("type")
            if expected is not None and not _matches_type(args[key], expected):
                errors.append(f"参数 {key} 类型不符，期望 {expected}")
        return errors

    def parse_output(self, raw: str, schema: dict[str, Any]) -> ParsedOutput:
        """把自由文本解析为结构化指令；失败抛 OUTPUT_PARSE_FAILED。"""
        try:
            instruction = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConstraintError(
                ConstraintErrorCode.OUTPUT_PARSE_FAILED, f"输出解析失败: {exc}"
            ) from exc
        if not isinstance(instruction, dict):
            raise ConstraintError(ConstraintErrorCode.OUTPUT_PARSE_FAILED, "输出解析失败: 非对象")
        return ParsedOutput(ok=True, instruction=cast(dict[str, Any], instruction))
