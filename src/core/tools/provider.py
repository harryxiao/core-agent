"""工具提供者（tool-use 核心）。

统一调用入口（invoke / ainvoke 同构）：schema 参数校验 → coeffect 解析
（缺失拒绝）→ 确认门（不可逆/高风险阻止）→ 执行（超时保护）→ 写类工具
效应记录（可逆撤销）；回滚委托 :class:`EffectTracker` 按 trace 逆序撤销。

对应接口：doc/03-interfaces/tool-use-interface.md §2
"""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, cast

from core.plugin_registry import (
    CoeffectMissing,
    CoeffectResolver,
    Effect,
    EffectTracker,
    RollbackReport,
)

from .errors import ToolErrorCode, ToolUseError
from .models import ToolDef, ToolError, ToolResult
from .safety_gate import SafetyGate
from .tool import Tool


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


class ToolProvider:
    """工具注册与统一调用入口。"""

    def __init__(
        self,
        coeffect_resolver: CoeffectResolver | None = None,
        effect_tracker: EffectTracker | None = None,
        gate: SafetyGate | None = None,
    ) -> None:
        self._resolver = coeffect_resolver if coeffect_resolver is not None else CoeffectResolver()
        self._tracker = effect_tracker if effect_tracker is not None else EffectTracker()
        self._gate = gate if gate is not None else SafetyGate()
        self._tools: dict[str, Tool] = {}
        self._warnings: list[str] = []

    def register(self, tool: Tool) -> None:
        """注册工具：schema 非法拒绝；声明/行为不符记录告警。"""
        schema = cast(Any, tool.definition.schema)
        if not isinstance(schema, dict):
            raise ToolUseError(
                ToolErrorCode.INVALID_TOOL_SCHEMA,
                f"工具 {tool.definition.tool_id} schema 非法（须为 dict）",
            )
        if tool.undo is not None and not any("write" in c for c in tool.definition.coeffects):
            self._warnings.append(
                f"工具 {tool.definition.tool_id} 有撤销闭包却未声明写类 coeffect，待复核"
            )
        self._tools[tool.definition.tool_id] = tool

    def unregister(self, tool_id: str) -> None:
        """卸载工具：对称于 register；不存在静默忽略（卸载幂等）。"""
        self._tools.pop(tool_id, None)

    @property
    def warnings(self) -> list[str]:
        """声明/行为不符告警列表（遥测观测到偏差后待复核）。"""
        return list(self._warnings)

    def active_tools(self) -> list[ToolDef]:
        """返回当前已注册工具的定义列表（供 loop 注入）。"""
        return [tool.definition for tool in self._tools.values()]

    def invoke(self, tool_id: str, args: dict[str, Any], *, trace_id: str) -> ToolResult:
        """同步统一调用入口：经事件循环桥接 ainvoke。"""
        return asyncio.run(self.ainvoke(tool_id, args, trace_id=trace_id))

    async def ainvoke(  # noqa: PLR0911 — 调用管道天然多早退分支
        self, tool_id: str, args: dict[str, Any], *, trace_id: str
    ) -> ToolResult:
        """异步统一调用入口（非阻塞，支持真并发）。"""
        tool = self._tools.get(tool_id)
        if tool is None:
            return ToolResult(
                ok=False,
                error=ToolError(ToolErrorCode.INVALID_ARGS, f"未知工具: {tool_id}"),
            )

        err = self._validate_args(tool, args)
        if err is not None:
            return ToolResult(ok=False, error=err)

        coeffects = tool.definition.coeffects
        try:
            self._resolver.resolve(coeffects)
        except CoeffectMissing as exc:
            return ToolResult(ok=False, error=ToolError(ToolErrorCode.COEFFECT_MISSING, str(exc)))

        decision = self._gate.confirm(tool_id, args, coeffects, tool.definition.reversible)
        if decision.action == "deny":
            return ToolResult(ok=False, error=ToolError(ToolErrorCode.GATE_DENIED, decision.reason))
        if decision.action == "confirm":
            return ToolResult(
                ok=False,
                error=ToolError(ToolErrorCode.IRREVERSIBLE_BLOCKED, decision.reason),
            )

        try:
            result = await asyncio.wait_for(
                self._call(tool, args), timeout=tool.definition.timeout_s
            )
        except TimeoutError:
            return ToolResult(
                ok=False, error=ToolError(ToolErrorCode.TIMEOUT, f"工具 {tool_id} 执行超时")
            )

        effect_id: str | None = None
        if tool.undo is not None:
            effect_id = self._tracker.record(
                Effect(
                    op=tool_id,
                    target=str(args.get("path") or tool_id),
                    undo=tool.undo,
                    reversible=tool.definition.reversible,
                    coeffect=coeffects,
                    trace_id=trace_id,
                    ts=time.time(),
                )
            )
        return ToolResult(ok=True, data=result, effect_id=effect_id)

    def rollback(self, trace_id: str | None = None) -> RollbackReport:
        """回滚：按 trace 逆序撤销该轮效应（None 则全局回滚）。"""
        return self._tracker.rollback(trace_id)

    # ---- 内部辅助 ----

    def _validate_args(self, tool: Tool, args: dict[str, Any]) -> ToolError | None:
        schema = tool.definition.schema
        missing = [k for k in schema.get("required", []) if k not in args]
        if missing:
            return ToolError(ToolErrorCode.INVALID_ARGS, f"缺少必需参数: {missing}")
        for key, spec in schema.get("properties", {}).items():
            if key not in args:
                continue
            expected = spec.get("type")
            if expected is None or _matches_type(args[key], expected):
                continue
            return ToolError(ToolErrorCode.INVALID_ARGS, f"参数 {key} 类型不符，期望 {expected}")
        return None

    async def _call(self, tool: Tool, args: dict[str, Any]) -> Any:
        result = tool.handler(**args)
        if inspect.isawaitable(result):
            result = await result
        return result
