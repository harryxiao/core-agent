"""MCP 远端工具结果的本地载荷契约（change 0319 / ADR-0309）。

经 ``InstallDispatcher`` 适配进本地工具面的 MCP 工具，其 ``ToolResult.data`` 必须是
**可 JSON 序列化**的恒定信封 ``{ok, data, code, error}``：观测记录用 ``json.dumps``
落盘（``DefaultLoop._record_observation``），不可序列化结果会直接崩掉整轮；远端失败
则经信封回喂模型，而不是冒充本地失败触发回滚。
"""

from __future__ import annotations

import json
from typing import Any

from core.mcp import FakeTransport, MCPClient
from core.plugin_registry import (
    CoeffectResolver,
    InstallableAsset,
    PluginKind,
    PluginSource,
)
from core.plugins import InstallDispatcher
from core.skills import SkillLibrary
from core.tools import ToolProvider

_ENVELOPE_KEYS = {"ok", "data", "code", "error"}


class _ScriptedTransport(FakeTransport):
    """按工具名脚本化 ``tools/call`` 应答：成功载荷 / ``isError`` 信封 / 协议层错误。"""

    def __init__(self) -> None:
        super().__init__()
        self.payloads: dict[str, Any] = {}
        self.is_errors: dict[str, str] = {}
        self.protocol_errors: set[str] = set()

    def call(self, method: str, params: dict[str, Any]) -> Any:
        if method != "tools/call":
            return super().call(method, params)
        self.calls.append((method, params))
        name = str(params.get("name"))
        if name in self.protocol_errors:
            raise KeyError(name)
        if name in self.is_errors:
            body = json.dumps({"code": "REMOTE_FAILED", "error": self.is_errors[name]})
            return {"content": [{"type": "text", "text": body}], "isError": True}
        payload = json.dumps(self.payloads.get(name, {"result": f"ok:{name}"}))
        return {"content": [{"type": "text", "text": payload}], "isError": False}


def _provider(transport: _ScriptedTransport, *tool_names: str) -> ToolProvider:
    resolver = CoeffectResolver()
    resolver.register("network:outbound", True)
    provider = ToolProvider(coeffect_resolver=resolver)
    for name in tool_names:
        transport.add_tool(name, f"{name} tool")
    dispatcher = InstallDispatcher(
        SkillLibrary(), provider, mcp_client=MCPClient(transport_factory=lambda ep: transport)
    )
    dispatcher.install(
        InstallableAsset(
            kind=PluginKind.MCP,
            source=PluginSource.MCP_ENDPOINT,
            manifest={"name": "files", "url": "https://example.com/mcp"},
        )
    )
    return provider


def _call(provider: ToolProvider, name: str) -> dict[str, Any]:
    result = provider.invoke(f"mcp.files.{name}", {"q": "x"}, trace_id="t1", approved=True)
    assert result.ok is True
    payload = result.data
    assert isinstance(payload, dict)
    # 观测记录落盘口径：必须可 JSON 序列化
    json.dumps({"data": payload}, ensure_ascii=False)
    return payload


def test_remote_tool_success_returns_serializable_envelope() -> None:
    transport = _ScriptedTransport()
    transport.payloads["search"] = {"result": "ok:search", "args": {"q": "x"}}
    provider = _provider(transport, "search")

    payload = _call(provider, "search")

    assert set(payload) == _ENVELOPE_KEYS
    assert payload["ok"] is True
    assert payload["data"] == {"result": "ok:search", "args": {"q": "x"}}
    assert payload["code"] is None
    assert payload["error"] is None


def test_remote_is_error_is_fed_back_not_raised() -> None:
    transport = _ScriptedTransport()
    transport.is_errors["index"] = "pipeline failed: bad repo_path"
    provider = _provider(transport, "index")

    payload = _call(provider, "index")

    assert set(payload) == _ENVELOPE_KEYS
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["code"] == "REMOTE_FAILED"
    assert payload["error"] == "pipeline failed: bad repo_path"


def test_remote_protocol_error_keeps_code() -> None:
    transport = _ScriptedTransport()
    transport.protocol_errors.add("search")
    provider = _provider(transport, "search")

    payload = _call(provider, "search")

    assert set(payload) == _ENVELOPE_KEYS
    assert payload["ok"] is False
    assert payload["code"] == "MCP_TOOL_NOT_FOUND"


def test_remote_reply_payload_is_not_terminal() -> None:
    transport = _ScriptedTransport()
    transport.payloads["search"] = {"reply": "远端载荷不得冒充终止回复"}
    provider = _provider(transport, "search")

    payload = _call(provider, "search")

    assert set(payload) == _ENVELOPE_KEYS
    assert "reply" not in payload
    assert payload["data"] == {"reply": "远端载荷不得冒充终止回复"}
