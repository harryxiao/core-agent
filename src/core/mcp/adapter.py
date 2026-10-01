"""MCP 工具适配器（mcp）。

把远端工具契约适配为本地 :class:`~core.tools.ToolDef`，``tool_id`` 形如
``mcp.<server>.<tool>``；同名重映射抛 TOOL_NAME_CONFLICT。

对应接口：doc/03-interfaces/mcp-interface.md §4
"""

from __future__ import annotations

from core.tools import ToolDef

from .errors import MCPError, MCPErrorCode
from .models import RemoteTool, ServerHandle


class MCPToolAdapter:
    """远程工具 → 本地 ToolDef 适配，跟踪已用 tool_id 防冲突。"""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def tool_id(self, remote: RemoteTool, handle: ServerHandle) -> str:
        """远程工具 → 本地 tool_id（纯函数，供 install/uninstall 对称复用）。"""
        return f"mcp.{handle.handle_id}.{remote.name}"

    def adapt(self, remote: RemoteTool, handle: ServerHandle) -> ToolDef:
        tool_id = self.tool_id(remote, handle)
        if tool_id in self._seen:
            raise MCPError(MCPErrorCode.TOOL_NAME_CONFLICT, f"工具名冲突: {tool_id}")
        self._seen.add(tool_id)
        return ToolDef(
            tool_id=tool_id,
            description=remote.description,
            schema=remote.inputSchema,
            coeffects=["network:outbound"],
            reversible=False,
        )
