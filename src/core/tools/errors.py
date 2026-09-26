"""工具领域错误码（tool-use）。

结构化错误码与异常分离：注册期非法定义抛 :class:`ToolUseError`（异常），
调用期失败经 :class:`~.models.ToolResult` 携带 :class:`~.models.ToolError`
返回（不抛异常），上层统一按 ``code`` 分支处理。

对应接口：doc/03-interfaces/tool-use-interface.md §5
"""

from __future__ import annotations

from enum import StrEnum


class ToolErrorCode(StrEnum):
    """工具结构化错误码。"""

    INVALID_TOOL_SCHEMA = "INVALID_TOOL_SCHEMA"
    INVALID_ARGS = "INVALID_ARGS"
    COEFFECT_MISSING = "COEFFECT_MISSING"
    GATE_DENIED = "GATE_DENIED"
    IRREVERSIBLE_BLOCKED = "IRREVERSIBLE_BLOCKED"
    TIMEOUT = "TIMEOUT"
    UNDO_FAILED = "UNDO_FAILED"


class ToolUseError(Exception):
    """注册期业务异常：携带结构化错误码与信息。"""

    def __init__(self, code: ToolErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
