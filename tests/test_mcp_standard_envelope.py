"""MCP 标准 envelope 双向对齐（change 0075 / 账本 B6）。

规格「MCP Server 模式」字面点名 Claude Code / Cursor 可直接挂载本 server，而实测**双向都不通**：
本 server 的 `tools/list` 应答是**裸列表**、`tools/call` 是**序列化 `CallResult` 直出**；
本 client 的 `initialize` params **为空**（对端 zod 校验直接拒），且 `RemoteTool(**item)`
遇标准应答的**容器键**会逐字符迭代、遇**厂商扩展字段**会 `TypeError`。

本文件以 `claude mcp serve` 的**实测形状**为基准（协议版本 `2024-11-05` 同源、
`{"tools": [...]}` 容器键、tool 对象带 12 个扩展键、成功应答**无** `isError` 键），
证明两侧均已对齐标准，且旧式**裸形状**应答仍可解析（向后兼容）。
"""

from __future__ import annotations

import io
import json
from typing import Any

from core.mcp import (
    PROTOCOL_VERSION,
    FakeTransport,
    MCPClient,
    MCPEndpoint,
    MCPServer,
)
from core.plugin_registry import CoeffectResolver
from core.tools import Tool, ToolDef, ToolProvider

# `claude mcp serve` 实测：tool 对象除 name/description/inputSchema 外还带扩展键。
_VENDOR_EXTRA: dict[str, Any] = {
    "searchHint": "hint",
    "aliases": ["R"],
    "backgrounding": "self",
    "maxResultSizeChars": 100000,
    "strict": True,
    "shouldDefer": False,
}

_READ_TOOL = {
    "name": "Read",
    "description": "read a file",
    "inputSchema": {"type": "object"},
    **_VENDOR_EXTRA,
}


class _StandardTransport:
    """标准 MCP 远端替身（形状对齐 `claude mcp serve` 实测）。"""

    def __init__(self, *, tool_result: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.connected = False
        self.tool_result = tool_result

    def connect(self, endpoint: MCPEndpoint) -> None:
        self.connected = True

    def ping(self) -> bool:
        return self.connected

    def close(self) -> None:
        self.connected = False

    def call(self, method: str, params: dict[str, Any]) -> Any:
        self.calls.append((method, params))
        if method == "initialize":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "claude/tengu", "version": "2.1.283"},
            }
        if method == "tools/list":
            return {"tools": [_READ_TOOL]}
        if method == "resources/list":
            return {"resources": [{"uri": "file:///x", "name": "x", "mimeType": "text/plain"}]}
        if method == "prompts/list":
            return {"prompts": [{"name": "p", "description": "d", "arguments": []}]}
        if method == "tools/call":
            return self.tool_result if self.tool_result is not None else _ok_envelope({"ok": 1})
        raise AssertionError(f"未预期的远端方法: {method}")  # noqa: TRY003 — 需携方法名


def _ok_envelope(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def _err_envelope(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": True}


def _endpoint() -> MCPEndpoint:
    return MCPEndpoint(transport="stdio", command="x")


def _client(transport: Any) -> MCPClient:
    return MCPClient(transport_factory=lambda ep: transport)


# ---- ① 握手：标准三元组（此前 params 为空 ⇒ 对端 -32603） ----


def test_initialize_sends_standard_handshake_params() -> None:
    transport = _StandardTransport()
    _client(transport).connect(_endpoint())
    method, params = transport.calls[0]
    assert method == "initialize"
    assert params["protocolVersion"] == PROTOCOL_VERSION
    assert params["capabilities"] == {}  # 必须存在且为对象（对端 zod 校验）
    assert params["clientInfo"]["name"] == "core-agent"
    assert params["clientInfo"]["version"]


# ---- ② 发现：标准容器键 + 容忍厂商扩展字段 ----


def test_standard_tools_list_is_parsed_with_vendor_fields_ignored() -> None:
    """`{"tools": [...]}` 容器键 + 扩展字段 ⇒ 取已知键、不报错。"""
    client = _client(_StandardTransport())
    handle = client.connect(_endpoint())
    tools = client.list_tools(handle)
    assert [t.name for t in tools] == ["Read"]
    assert tools[0].description == "read a file"
    assert tools[0].inputSchema == {"type": "object"}


def test_standard_resources_and_prompts_container_keys() -> None:
    client = _client(_StandardTransport())
    handle = client.connect(_endpoint())
    assert [r.uri for r in client.list_resources(handle)] == ["file:///x"]
    assert [p.name for p in client.list_prompts(handle)] == ["p"]


def test_bare_list_response_still_parsed() -> None:
    """旧式**裸列表**应答（仓内 echo 夹具形状）仍可解析 —— 旧服务端不挂。"""
    transport = FakeTransport()
    transport.add_tool("echo", "d")
    client = _client(transport)
    handle = client.connect(_endpoint())
    assert [t.name for t in client.list_tools(handle)] == ["echo"]


# ---- ③ 调用：标准结果信封归一 ----


def test_tools_call_success_is_normalized() -> None:
    transport = _StandardTransport(tool_result=_ok_envelope({"content": "hi"}))
    client = _client(transport)
    handle = client.connect(_endpoint())
    result = client.call_tool(handle, "Read", {"file_path": "/x"})
    assert result.ok is True
    assert result.data == {"content": "hi"}


def test_tools_call_error_flag_is_normalized_with_structured_code() -> None:
    """`isError: true` ⇒ ok=False，并还原载荷里的结构化错误码。"""
    transport = _StandardTransport(
        tool_result=_err_envelope({"code": "PERMISSION_DENIED", "error": "未授权工具: X"})
    )
    client = _client(transport)
    handle = client.connect(_endpoint())
    result = client.call_tool(handle, "X", {})
    assert result.ok is False
    assert result.code == "PERMISSION_DENIED"
    assert result.error == "未授权工具: X"


def test_tools_call_error_flag_with_plain_text() -> None:
    """`isError` 且文本**非 JSON**（厂商自由文本）⇒ 原样承载为错误信息。"""
    transport = _StandardTransport(
        tool_result={"content": [{"type": "text", "text": "boom"}], "isError": True}
    )
    client = _client(transport)
    handle = client.connect(_endpoint())
    result = client.call_tool(handle, "X", {})
    assert result.ok is False
    assert result.code is None
    assert result.error == "boom"


def test_tools_call_non_json_text_is_carried_verbatim() -> None:
    """标准服务端回**纯文本**（非 JSON）⇒ 原样承载，不做解码。"""
    transport = _StandardTransport(
        tool_result={"content": [{"type": "text", "text": "hello"}], "isError": False}
    )
    client = _client(transport)
    handle = client.connect(_endpoint())
    result = client.call_tool(handle, "Read", {})
    assert result.ok is True
    assert result.data == "hello"


def test_legacy_call_result_shape_still_carried() -> None:
    """旧式应答（非标准信封，如 echo 夹具的裸对象）⇒ 原样承载，不抛。"""
    transport = _StandardTransport(tool_result={"result": "ok", "args": {"x": 1}})
    client = _client(transport)
    handle = client.connect(_endpoint())
    result = client.call_tool(handle, "echo", {"x": 1})
    assert result.ok is True
    assert result.data == {"result": "ok", "args": {"x": 1}}


# ---- ④ server 侧 wire 形状（事件循环的**字面**应答帧） ----


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


def _feed(*messages: dict[str, Any]) -> list[dict[str, Any]]:
    stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
    stdout = io.StringIO()
    MCPServer(tool_provider=_provider()).serve_stdio(
        MCPEndpoint(transport="stdio", session_id="s1"), stdin=stdin, stdout=stdout
    )
    return [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]


def _req(rid: int, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}


def test_server_tools_list_uses_container_key() -> None:
    (response,) = _feed(_req(1, "tools/list"))
    assert response["result"] == {
        "tools": [
            {
                "name": "core.tools.file_read",
                "description": "read",
                "inputSchema": {"type": "object"},
            }
        ]
    }


def test_server_tools_call_success_envelope() -> None:
    (response,) = _feed(
        _req(1, "tools/call", {"name": "core.tools.file_read", "arguments": {"path": "/x"}})
    )
    result = response["result"]
    assert set(result) == {"content", "isError"}
    assert result["isError"] is False
    assert result["content"][0]["type"] == "text"
    assert json.loads(result["content"][0]["text"]) == {"content": "x"}  # 载荷往返


def test_server_tools_call_denied_envelope() -> None:
    (response,) = _feed(_req(1, "tools/call", {"name": "core.tools.file_write", "arguments": {}}))
    result = response["result"]
    assert result["isError"] is True
    payload = json.loads(result["content"][0]["text"])
    assert payload["code"] == "PERMISSION_DENIED"  # 结构化错误码可还原


def test_server_initialize_envelope_is_standard() -> None:
    (response,) = _feed(_req(1, "initialize"))
    result = response["result"]
    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert isinstance(result["capabilities"], dict)
    assert result["serverInfo"]["name"] == "core-agent"


# ---- ⑤ 自环：server 的**真实应答帧**喂回 client（两端同源，往返保真） ----


def test_self_round_trip_success() -> None:
    (response,) = _feed(
        _req(1, "tools/call", {"name": "core.tools.file_read", "arguments": {"path": "/x"}})
    )
    client = _client(_StandardTransport(tool_result=response["result"]))
    handle = client.connect(_endpoint())
    result = client.call_tool(handle, "core.tools.file_read", {"path": "/x"})
    assert result.ok is True
    assert result.data == {"content": "x"}  # 载荷往返逐位相同


def test_self_round_trip_denied_keeps_code() -> None:
    (response,) = _feed(_req(1, "tools/call", {"name": "core.tools.file_write", "arguments": {}}))
    client = _client(_StandardTransport(tool_result=response["result"]))
    handle = client.connect(_endpoint())
    result = client.call_tool(handle, "core.tools.file_write", {})
    assert result.ok is False
    assert result.code == "PERMISSION_DENIED"  # 结构化错误码经 wire 往返后仍可还原
