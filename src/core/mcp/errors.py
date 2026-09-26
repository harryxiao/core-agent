"""MCP 领域错误码（mcp）。

结构化错误码与异常分离：连接 / 协议 / 工具 / 超时 / 权限 / 熔断 / 冲突。

对应接口：doc/03-interfaces/mcp-interface.md §6
"""

from __future__ import annotations

from enum import StrEnum


class MCPErrorCode(StrEnum):
    """MCP 结构化错误码。"""

    MCP_CONNECT_FAILED = "MCP_CONNECT_FAILED"
    MCP_PROTOCOL_MISMATCH = "MCP_PROTOCOL_MISMATCH"
    MCP_TOOL_NOT_FOUND = "MCP_TOOL_NOT_FOUND"
    REMOTE_TIMEOUT = "REMOTE_TIMEOUT"
    REMOTE_IRREVERSIBLE = "REMOTE_IRREVERSIBLE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    MCP_UNAVAILABLE = "MCP_UNAVAILABLE"
    TOOL_NAME_CONFLICT = "TOOL_NAME_CONFLICT"


class MCPError(Exception):
    """MCP 业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: MCPErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
