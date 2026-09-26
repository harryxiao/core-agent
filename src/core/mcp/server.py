"""MCP 服务端（mcp）。

把本地 :class:`~core.tools.ToolProvider` 以最小暴露面（默认只读类，白名单
显式开放）提供给远端；调用复用 ToolProvider.invoke 链路，越权返回
PERMISSION_DENIED；单连接多会话经 session_id 分流。

对应接口：doc/03-interfaces/mcp-interface.md §5
"""

from __future__ import annotations

import uuid
from typing import Any

from core.tools import ToolDef, ToolProvider

from .errors import MCPErrorCode
from .models import CallResult, MCPEndpoint, MCPTool, ServerCapabilities, ServerConnection
from .transport import Transport

_PLUGIN_ID = "mcp.server"
_GENERATION = 1
_DEFAULT_SCHEMA: dict[str, Any] = {"type": "object"}


class MCPServer:
    """MCP 服务端插件：本地工具以最小暴露面供远端调用。"""

    plugin_id = _PLUGIN_ID
    generation = _GENERATION
    schema = _DEFAULT_SCHEMA
    coeffects: list[str] = []

    def __init__(
        self, tool_provider: ToolProvider | None = None, whitelist: list[str] | None = None
    ) -> None:
        self._tool_provider = tool_provider
        self._whitelist = set(whitelist or [])
        self._connections: dict[str, ServerConnection] = {}

    def load(self) -> None:
        return None

    def unload(self) -> None:
        self._connections.clear()

    def check(self) -> bool:
        return True

    def serve(self, transport: Transport, endpoint: MCPEndpoint) -> ServerConnection:
        """绑定传输并返回服务连接（stdio/http 事件循环在 M2 接入）。"""
        connection = ServerConnection(
            connection_id=uuid.uuid4().hex,
            session_id=endpoint.session_id,
            client_id=endpoint.session_id or "local",
        )
        self._connections[connection.connection_id] = connection
        return connection

    def route(self, session_id: str) -> ServerConnection | None:
        for connection in self._connections.values():
            if connection.session_id == session_id:
                return connection
        return None

    def initialize(self, connection: ServerConnection) -> ServerCapabilities:
        self._connections[connection.connection_id] = connection
        tools = self.list_tools(connection)
        return ServerCapabilities(tools=[t.name for t in tools], resources=[])

    def list_tools(self, connection: ServerConnection) -> list[MCPTool]:
        if self._tool_provider is None:
            return []
        exposed: list[MCPTool] = []
        for tool_def in self._tool_provider.active_tools():
            if self._whitelist:
                if tool_def.tool_id not in self._whitelist:
                    continue
            elif not self._is_readonly(tool_def):
                continue  # 默认最小暴露：只暴露只读类
            exposed.append(
                MCPTool(
                    name=tool_def.tool_id,
                    description=tool_def.description,
                    inputSchema=tool_def.schema,
                )
            )
        return exposed

    def call_tool(
        self, connection: ServerConnection, name: str, args: dict[str, Any]
    ) -> CallResult:
        exposed = {tool.name for tool in self.list_tools(connection)}
        if name not in exposed:
            return CallResult(
                ok=False, code=MCPErrorCode.PERMISSION_DENIED.value, error=f"未授权工具: {name}"
            )
        if self._tool_provider is None:
            return CallResult(
                ok=False, code=MCPErrorCode.MCP_UNAVAILABLE.value, error="无工具提供者"
            )
        result = self._tool_provider.invoke(name, args, trace_id=f"external:{connection.client_id}")
        if result.ok:
            return CallResult(ok=True, data=result.data)
        code = result.error.code if result.error is not None else None
        error = result.error.message if result.error is not None else None
        return CallResult(ok=False, code=code, error=error)

    def _is_readonly(self, tool_def: ToolDef) -> bool:
        return not any("write" in c for c in tool_def.coeffects)
