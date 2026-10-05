"""MCP stdio 传输 + 安装分流 + 消费侧安全（change 0054 / 账本 B1-M2）。

用**真实子进程**（stdlib echo MCP server）证明 stdio 传输端到端可用（握手 / 工具发现 / 调用 /
销毁 / 超时），用替身证明 http 白名单守卫与 SDK 缺失降级；最后以 `PermissionGuard` 证明
适配后的远端工具走确认门。
"""

from __future__ import annotations

import sys

import pytest

from core.mcp import (
    FakeTransport,
    MCPClient,
    MCPEndpoint,
    MCPError,
    MCPErrorCode,
    MCPToolAdapter,
    RemoteTool,
    ServerHandle,
    build_transport,
)
from core.mcp.transport import StdioTransport, build_http_transport, map_remote_error
from core.permission import PermissionGuard, ResourceBudget, SandboxPolicy

# 最小 stdlib MCP 服务端：换行分帧 JSON-RPC，仅实现 initialize / tools/list / tools/call。
_ECHO_SERVER = """
import json, sys
def send(obj):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    rid = msg.get("id")
    if rid is None:
        continue  # notification（notifications/initialized）无需响应
    method = msg.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2024-11-05"}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": rid, "result": [
            {"name": "echo", "description": "d", "inputSchema": {"type": "object"}}]})
    elif method == "tools/call":
        name = msg["params"]["name"]
        if name != "echo":
            send({"jsonrpc": "2.0", "id": rid,
                  "error": {"code": -32603, "message": "Tool %s not found" % name}})
        else:
            args = msg["params"]["arguments"]
            send({"jsonrpc": "2.0", "id": rid, "result": {"result": "ok", "args": args}})
    else:
        send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": method}})
"""


def _stdio_endpoint() -> MCPEndpoint:
    return MCPEndpoint(transport="stdio", command=sys.executable, args=["-c", _ECHO_SERVER])


# ---- stdio 传输端到端（真实子进程） ----


def test_stdio_transport_handshake_and_tool_call() -> None:
    """连接握手 → 工具发现 → 调用，请求/响应按 id 配对。"""
    client = MCPClient()  # 不注入 factory → 走生产 build_transport 分派
    handle = client.connect(_stdio_endpoint())
    try:
        tools = client.list_tools(handle)
        assert [t.name for t in tools] == ["echo"]
        result = client.call_tool(handle, "echo", {"x": 1})
        assert result.ok is True
        assert result.data["result"] == "ok"
        assert result.data["args"] == {"x": 1}
    finally:
        client.close(handle)


def test_stdio_unknown_tool_maps_to_tool_not_found() -> None:
    """账本 B8：远端对未知工具回 JSON-RPC 错误 → MCP_TOOL_NOT_FOUND（非 MCP_UNAVAILABLE）。"""
    client = MCPClient()
    handle = client.connect(_stdio_endpoint())
    try:
        result = client.call_tool(handle, "nope", {})
        assert result.ok is False
        assert result.code == MCPErrorCode.MCP_TOOL_NOT_FOUND.value
    finally:
        client.close(handle)


def test_stdio_unknown_method_maps_to_protocol_mismatch() -> None:
    """账本 B8：远端对不支持的方法回 -32601 → MCP_PROTOCOL_MISMATCH。"""
    client = MCPClient()
    handle = client.connect(_stdio_endpoint())
    try:
        with pytest.raises(MCPError) as exc_info:
            client.read_resource(handle, "file:///x")  # 远端未实现 resources/read
        assert exc_info.value.code is MCPErrorCode.MCP_PROTOCOL_MISMATCH
    finally:
        client.close(handle)


def test_stdio_transport_close_terminates_subprocess() -> None:
    """close 终止并回收子进程（无残留）。"""
    client = MCPClient()
    handle = client.connect(_stdio_endpoint())
    transport = client._transports[handle.handle_id]  # noqa: SLF001 — 接线断言
    assert transport.ping() is True
    client.close(handle)
    assert transport.ping() is False


def test_stdio_transport_timeout_is_structured() -> None:
    """服务端不响应 → REMOTE_TIMEOUT，不永久阻塞；连接失败即回收子进程。"""
    endpoint = MCPEndpoint(
        transport="stdio", command=sys.executable, args=["-c", "import time; time.sleep(60)"]
    )
    client = MCPClient(budget=ResourceBudget(timeout_s=0.5))
    with pytest.raises(MCPError) as exc_info:
        client.connect(endpoint)
    assert exc_info.value.code is MCPErrorCode.REMOTE_TIMEOUT
    assert client._transports == {}  # noqa: SLF001 — 失败不留半开连接


# ---- build_transport 分派 ----


def test_build_transport_dispatches_stdio() -> None:
    assert isinstance(build_transport(_stdio_endpoint()), StdioTransport)


def test_build_transport_unknown_kind_is_structured() -> None:
    with pytest.raises(MCPError) as exc_info:
        build_transport(MCPEndpoint(transport="carrier-pigeon"))  # type: ignore[arg-type]
    assert exc_info.value.code is MCPErrorCode.MCP_CONNECT_FAILED


# ---- http 出站守卫 + SDK 降级 ----


def test_http_transport_rejects_non_allowlisted_host() -> None:
    """非白名单 host → PERMISSION_DENIED，不建立连接。"""
    endpoint = MCPEndpoint(transport="http", url="https://evil.example.com/mcp")
    policy = SandboxPolicy(host_allowlist=["good.example.com"])
    with pytest.raises(MCPError) as exc_info:
        build_http_transport(endpoint, policy)
    assert exc_info.value.code is MCPErrorCode.PERMISSION_DENIED


def test_http_transport_missing_sdk_gives_install_hint(monkeypatch) -> None:
    """白名单内 + 未装 SDK → MCP_CONNECT_FAILED 且提示安装可选依赖。"""
    monkeypatch.setattr("importlib.util.find_spec", lambda name: None)
    endpoint = MCPEndpoint(transport="http", url="https://good.example.com/mcp")
    policy = SandboxPolicy(host_allowlist=["good.example.com"])
    with pytest.raises(MCPError) as exc_info:
        build_http_transport(endpoint, policy)
    assert exc_info.value.code is MCPErrorCode.MCP_CONNECT_FAILED
    assert "core-agent[mcp]" in exc_info.value.message


def test_http_transport_with_sdk_reports_session_pending(monkeypatch) -> None:
    """白名单内 + 已装 SDK → 明确「会话待接入」（不写未验证的投机适配）。"""
    monkeypatch.setattr("importlib.util.find_spec", lambda name: object())
    endpoint = MCPEndpoint(transport="streamable-http", url="https://good.example.com/mcp")
    policy = SandboxPolicy(host_allowlist=["good.example.com"])
    with pytest.raises(MCPError) as exc_info:
        build_http_transport(endpoint, policy)
    assert exc_info.value.code is MCPErrorCode.MCP_CONNECT_FAILED
    assert "待接入" in exc_info.value.message


# ---- add 按来源分流 ----


def _spy_client() -> tuple[MCPClient, list[MCPEndpoint]]:
    seen: list[MCPEndpoint] = []

    def factory(endpoint: MCPEndpoint) -> FakeTransport:
        seen.append(endpoint)
        return FakeTransport()

    return MCPClient(transport_factory=factory), seen


def test_add_url_source_builds_http_endpoint() -> None:
    client, seen = _spy_client()
    client.add("https://example.com/mcp", "files")
    assert seen[0].transport == "http"
    assert seen[0].url == "https://example.com/mcp"


def test_add_command_source_builds_stdio_endpoint() -> None:
    client, seen = _spy_client()
    client.add("npx -y server /tmp", "fs")
    assert seen[0].transport == "stdio"
    assert seen[0].command == "npx"
    assert seen[0].args == ["-y", "server", "/tmp"]


def test_add_explicit_command_overrides_shape() -> None:
    client, seen = _spy_client()
    client.add("ignored", "x", transport="stdio", command="uvx mcp-server", args=["--flag"])
    assert seen[0].transport == "stdio"
    assert seen[0].command == "uvx"
    assert seen[0].args == ["mcp-server", "--flag"]


# ---- 远端 JSON-RPC 错误码映射（账本 B8） ----


@pytest.mark.parametrize(
    ("method", "code", "expected"),
    [
        ("tools/call", -32603, MCPErrorCode.MCP_TOOL_NOT_FOUND),
        ("tools/call", -32602, MCPErrorCode.MCP_TOOL_NOT_FOUND),
        ("tools/call", -32601, MCPErrorCode.MCP_TOOL_NOT_FOUND),
        ("tools/list", -32700, MCPErrorCode.MCP_PROTOCOL_MISMATCH),
        ("tools/list", -32600, MCPErrorCode.MCP_PROTOCOL_MISMATCH),
        ("tools/list", -32601, MCPErrorCode.MCP_PROTOCOL_MISMATCH),
        ("resources/read", -32602, MCPErrorCode.MCP_PROTOCOL_MISMATCH),
        ("tools/list", -32603, MCPErrorCode.MCP_UNAVAILABLE),
        ("tools/list", 12345, MCPErrorCode.MCP_UNAVAILABLE),
        ("tools/list", None, MCPErrorCode.MCP_UNAVAILABLE),
    ],
)
def test_map_remote_error_table(method: str, code: object, expected: MCPErrorCode) -> None:
    """方法 + 标准码 → 本地结构化码；原始码与消息保留在文本中。"""
    error = {"code": code, "message": "boom"}
    mapped = map_remote_error(method, error)
    assert mapped.code is expected
    assert "boom" in mapped.message
    assert str(code) in mapped.message


def test_map_remote_error_tolerates_malformed_error() -> None:
    """非 dict 的 error 字段不得抛裸异常（结构化兜底）。"""
    mapped = map_remote_error("tools/list", "raw string error")
    assert mapped.code is MCPErrorCode.MCP_UNAVAILABLE


# ---- 结构化错误码不被重包 ----


def test_call_preserves_transport_error_code() -> None:
    """传输层抛出的 MCPError 直通（不被兜底分支重包为 MCP_UNAVAILABLE）。"""

    class _Timeout(FakeTransport):
        def call(self, method: str, params: dict) -> object:
            if method == "tools/list":
                raise MCPError(MCPErrorCode.REMOTE_TIMEOUT, "slow")
            return super().call(method, params)

    client = MCPClient(transport_factory=lambda ep: _Timeout())
    handle = client.connect(MCPEndpoint(transport="stdio", command="x"))
    with pytest.raises(MCPError) as exc_info:
        client.list_tools(handle)
    assert exc_info.value.code is MCPErrorCode.REMOTE_TIMEOUT


# ---- 消费侧确认门（远程工具高危确认） ----


def test_adapted_mcp_tool_triggers_confirm_gate() -> None:
    """适配后的远端工具（coeffects=network:outbound, reversible=False）走确认门。"""
    adapter = MCPToolAdapter()
    handle = ServerHandle(
        handle_id="h1", endpoint=MCPEndpoint(transport="http", url="https://x/mcp")
    )
    definition = adapter.adapt(
        RemoteTool(name="write_file", description="d", inputSchema={"type": "object"}), handle
    )
    assert definition.reversible is False
    assert "network:outbound" in definition.coeffects
    decision = PermissionGuard(mode="interactive").confirm(
        definition.tool_id, {}, definition.coeffects, definition.reversible
    )
    assert decision.action == "confirm"
