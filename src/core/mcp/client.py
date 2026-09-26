"""MCP 客户端（mcp）。

连接管理 / 工具发现 / 调用转发 / 心跳保活 / 断线重连 / 异常隔离。

- ``connect`` 失败抛 MCP_CONNECT_FAILED，协议不匹配抛 MCP_PROTOCOL_MISMATCH。
- ``call_tool`` 远端异常隔离：不向调用方抛裸异常，返回 CallResult 承载错误码。
- 心跳失效 / 连接断开时自动重连。

对应接口：doc/03-interfaces/mcp-interface.md §3
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from core.plugin_registry import PluginSource

from .errors import MCPError, MCPErrorCode
from .models import (
    CallResult,
    MCPEndpoint,
    RemotePrompt,
    RemoteResource,
    RemoteTool,
    ServerHandle,
)
from .transport import Transport, build_transport

_PLUGIN_ID = "mcp.client"
_GENERATION = 1
_PROTOCOL_VERSION = "2024-11-05"
_DEFAULT_SCHEMA: dict[str, Any] = {"type": "object"}


class MCPClient:
    """MCP 客户端插件：经可注入传输与远端 MCP 服务通信。"""

    plugin_id = _PLUGIN_ID
    generation = _GENERATION
    schema = _DEFAULT_SCHEMA
    coeffects: list[str] = []

    def __init__(self, transport_factory: Callable[[MCPEndpoint], Transport] | None = None) -> None:
        self._transport_factory = transport_factory
        self._transports: dict[str, Transport] = {}
        self._endpoints: dict[str, MCPEndpoint] = {}
        self._named: dict[str, ServerHandle] = {}
        self._sources: dict[str, PluginSource] = {}

    def load(self) -> None:
        return None

    def unload(self) -> None:
        for transport in self._transports.values():
            transport.close()
        self._transports.clear()
        self._endpoints.clear()
        self._named.clear()
        self._sources.clear()

    def check(self) -> bool:
        return True

    def connect(self, endpoint: MCPEndpoint) -> ServerHandle:
        transport = self._make_transport(endpoint)
        try:
            transport.connect(endpoint)
            info = transport.call("initialize", {})
        except MCPError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise MCPError(MCPErrorCode.MCP_CONNECT_FAILED, f"连接失败: {exc}") from exc
        version = info.get("protocolVersion")
        if version != _PROTOCOL_VERSION:
            transport.close()
            raise MCPError(MCPErrorCode.MCP_PROTOCOL_MISMATCH, f"协议版本不匹配: {version}")
        handle = ServerHandle(handle_id=uuid.uuid4().hex, endpoint=endpoint)
        self._transports[handle.handle_id] = transport
        self._endpoints[handle.handle_id] = endpoint
        return handle

    def list_tools(self, handle: ServerHandle) -> list[RemoteTool]:
        raw = self._call(handle, "tools/list", {})
        return [RemoteTool(**item) for item in raw]

    def list_resources(self, handle: ServerHandle) -> list[RemoteResource]:
        raw = self._call(handle, "resources/list", {})
        return [RemoteResource(**item) for item in raw]

    def list_prompts(self, handle: ServerHandle) -> list[RemotePrompt]:
        raw = self._call(handle, "prompts/list", {})
        return [RemotePrompt(**item) for item in raw]

    def call_tool(self, handle: ServerHandle, name: str, args: dict[str, Any]) -> CallResult:
        try:
            data = self._call(handle, "tools/call", {"name": name, "arguments": args})
        except MCPError as exc:
            return CallResult(ok=False, code=exc.code.value, error=exc.message)
        return CallResult(ok=True, data=data)

    def read_resource(self, handle: ServerHandle, uri: str) -> str:
        data = self._call(handle, "resources/read", {"uri": uri})
        return str(data["content"])

    def get_prompt(self, handle: ServerHandle, name: str, args: dict[str, Any]) -> str:
        data = self._call(handle, "prompts/get", {"name": name, "arguments": args})
        return str(data["text"])

    def heartbeat(self, handle: ServerHandle) -> bool:
        transport = self._transports.get(handle.handle_id)
        if transport is None:
            return False
        try:
            alive = transport.ping()
        except Exception:  # noqa: BLE001 — 探活异常视为心跳失效
            return False
        if alive:
            return True
        try:
            transport.connect(self._endpoints[handle.handle_id])
        except Exception:  # noqa: BLE001 — 重连失败即心跳失效
            return False
        return True

    def close(self, handle: ServerHandle) -> None:
        transport = self._transports.pop(handle.handle_id, None)
        if transport is not None:
            transport.close()

    def add(self, source: str, name: str) -> ServerHandle:
        """mcp add：以 mcp-endpoint 来源（PluginSource.MCP_ENDPOINT）安装并连接，按 name 登记。

        discover → verify → install → register 收敛为「构建端点 + 连接 + 登记」，
        之后进入现有连接管理（心跳 / 复用逻辑不改）。
        """
        endpoint = MCPEndpoint(transport="http", url=source)
        handle = self.connect(endpoint)
        self._named[name] = handle
        self._sources[name] = PluginSource.MCP_ENDPOINT
        return handle

    def remove(self, name: str) -> None:
        """mcp remove：停用并卸载该服务端，释放连接 / 会话 / socket 资源。"""
        handle = self._named.pop(name, None)
        self._sources.pop(name, None)
        if handle is not None:
            self.close(handle)

    def named(self, name: str) -> ServerHandle | None:
        """按安装名查已登记的服务句柄。"""
        return self._named.get(name)

    def _make_transport(self, endpoint: MCPEndpoint) -> Transport:
        if self._transport_factory is not None:
            return self._transport_factory(endpoint)
        return build_transport(endpoint)

    def _call(self, handle: ServerHandle, method: str, params: dict[str, Any]) -> Any:
        transport = self._transports.get(handle.handle_id)
        if transport is None:
            raise MCPError(MCPErrorCode.MCP_UNAVAILABLE, "连接不存在")
        try:
            alive = transport.ping()
        except Exception as exc:  # noqa: BLE001 — 探活异常视为远端不可用
            raise MCPError(MCPErrorCode.MCP_UNAVAILABLE, f"心跳失效: {exc}") from exc
        if not alive:
            try:
                transport.connect(self._endpoints[handle.handle_id])
            except Exception as exc:  # noqa: BLE001
                raise MCPError(MCPErrorCode.MCP_UNAVAILABLE, f"重连失败: {exc}") from exc
        try:
            return transport.call(method, params)
        except KeyError as exc:
            raise MCPError(MCPErrorCode.MCP_TOOL_NOT_FOUND, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise MCPError(MCPErrorCode.MCP_UNAVAILABLE, f"远端不可用: {exc}") from exc
