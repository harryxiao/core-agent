"""mcp 单元测试（对齐规格场景 + §7 专属校验锚点）。

覆盖：连接失败/协议不匹配、工具适配与重名冲突、调用转发与异常隔离、
断线重连与心跳、server 最小暴露/白名单/越权、单连接多会话分流。
"""

from __future__ import annotations

import pytest

from core.mcp import (
    FakeTransport,
    MCPClient,
    MCPEndpoint,
    MCPError,
    MCPErrorCode,
    MCPServer,
    MCPToolAdapter,
    RemoteTool,
    ServerConnection,
    ServerHandle,
)
from core.plugin_registry import CoeffectResolver
from core.tools import Tool, ToolDef, ToolProvider


def _endpoint() -> MCPEndpoint:
    return MCPEndpoint(transport="stdio", command="mcp-server")


def _client(factory) -> MCPClient:
    return MCPClient(transport_factory=factory)


def _conn(session_id: str = "s1", connection_id: str = "c1") -> ServerConnection:
    return ServerConnection(
        connection_id=connection_id, session_id=session_id, client_id=session_id
    )


def _provider() -> ToolProvider:
    resolver = CoeffectResolver()
    resolver.register("filesystem:read", True)
    resolver.register("filesystem:write", True)
    provider = ToolProvider(coeffect_resolver=resolver)
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.file_read",
                description="read",
                schema={"type": "object"},
                coeffects=["filesystem:read"],
                reversible=False,
            ),
            handler=lambda path: {"content": "x"},
        )
    )
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.file_write",
                description="write",
                schema={"type": "object"},
                coeffects=["filesystem:write"],
                reversible=False,
            ),
            handler=lambda path, content: True,
        )
    )
    return provider


# ---- 连接 ----


def test_connect_failed() -> None:
    client = _client(lambda ep: FakeTransport(fail_connect=True))
    with pytest.raises(MCPError) as exc_info:
        client.connect(_endpoint())
    assert exc_info.value.code is MCPErrorCode.MCP_CONNECT_FAILED


def test_protocol_mismatch() -> None:
    client = _client(lambda ep: FakeTransport(protocol_version="1999-01-01"))
    with pytest.raises(MCPError) as exc_info:
        client.connect(_endpoint())
    assert exc_info.value.code is MCPErrorCode.MCP_PROTOCOL_MISMATCH


# ---- 适配 ----


def test_adapter_tool_id_and_conflict() -> None:
    adapter = MCPToolAdapter()
    handle = ServerHandle(handle_id="h1", endpoint=_endpoint())
    remote = RemoteTool(name="search", description="d", inputSchema={"type": "object"})
    tool_def = adapter.adapt(remote, handle)
    assert tool_def.tool_id == "mcp.h1.search"
    with pytest.raises(MCPError) as exc_info:
        adapter.adapt(remote, handle)  # 重名
    assert exc_info.value.code is MCPErrorCode.TOOL_NAME_CONFLICT


# ---- 调用转发 + 异常隔离 ----


def test_call_tool_forwards() -> None:
    transport = FakeTransport()
    transport.add_tool("search", "d")
    client = _client(lambda ep: transport)
    handle = client.connect(_endpoint())
    result = client.call_tool(handle, "search", {"q": "x"})
    assert result.ok is True
    assert result.data["result"] == "ok:search"


def test_call_tool_isolates_remote_failure() -> None:
    transport = FakeTransport()
    transport.add_tool("search", "d")
    transport.fail_methods.add("tools/call")
    client = _client(lambda ep: transport)
    handle = client.connect(_endpoint())
    result = client.call_tool(handle, "search", {})  # 不抛裸异常
    assert result.ok is False
    assert result.code == MCPErrorCode.MCP_UNAVAILABLE.value


def test_call_tool_not_found() -> None:
    transport = FakeTransport()
    client = _client(lambda ep: transport)
    handle = client.connect(_endpoint())
    result = client.call_tool(handle, "nope", {})
    assert result.ok is False
    assert result.code == MCPErrorCode.MCP_TOOL_NOT_FOUND.value


def test_call_tool_ping_exception_maps_to_unavailable() -> None:
    transport = FakeTransport(fail_ping=True)
    transport.add_tool("search", "d")
    client = _client(lambda ep: transport)
    handle = client.connect(_endpoint())
    result = client.call_tool(handle, "search", {})  # 探活抛异常 → 隔离为 MCP_UNAVAILABLE
    assert result.ok is False
    assert result.code == MCPErrorCode.MCP_UNAVAILABLE.value


# ---- 断线重连 + 心跳 ----


def test_reconnect_on_dead_transport() -> None:
    transport = FakeTransport()
    transport.add_tool("search", "d")
    client = _client(lambda ep: transport)
    handle = client.connect(_endpoint())
    transport.connected = False  # 模拟断线
    result = client.call_tool(handle, "search", {})  # 自动重连
    assert result.ok is True


def test_heartbeat_reconnects() -> None:
    transport = FakeTransport()
    client = _client(lambda ep: transport)
    handle = client.connect(_endpoint())
    transport.connected = False
    assert client.heartbeat(handle) is True
    assert transport.connected is True


def test_heartbeat_ping_exception_fails_closed() -> None:
    transport = FakeTransport(fail_ping=True)
    client = _client(lambda ep: transport)
    handle = client.connect(_endpoint())
    assert client.heartbeat(handle) is False  # 探活抛异常 → 心跳失效，不冒泡


# ---- server ----


def test_server_minimal_exposure() -> None:
    server = MCPServer(tool_provider=_provider())
    assert {t.name for t in server.list_tools(_conn())} == {"tools.file_read"}


def test_server_whitelist() -> None:
    server = MCPServer(tool_provider=_provider(), whitelist=["tools.file_write"])
    assert {t.name for t in server.list_tools(_conn())} == {"tools.file_write"}


def test_server_unauthorized_tool() -> None:
    server = MCPServer(tool_provider=_provider())
    result = server.call_tool(_conn(), "tools.file_write", {})
    assert result.ok is False
    assert result.code == MCPErrorCode.PERMISSION_DENIED.value


def test_server_call_tool_authorized() -> None:
    server = MCPServer(tool_provider=_provider())
    result = server.call_tool(_conn(), "tools.file_read", {"path": "/tmp/x"})
    assert result.ok is True
    assert result.data == {"content": "x"}


# ---- 多会话分流 ----


def test_server_session_routing() -> None:
    server = MCPServer(tool_provider=_provider())
    conn_a = _conn(session_id="s1", connection_id="c1")
    conn_b = _conn(session_id="s2", connection_id="c2")
    server.initialize(conn_a)
    server.initialize(conn_b)
    assert server.route("s1") is conn_a
    assert server.route("s2") is conn_b
    assert server.route("nope") is None
