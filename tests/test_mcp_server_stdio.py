"""MCP Server 模式 stdio 事件循环（change 0073 / 账本 B3）。

规格「MCP Server 模式」场景「stdio 本地挂载」要求外部 agent 拉起本 server → 握手 → 拿工具
列表 → 可调用；「工具暴露与白名单」要求**命名空间隔离**（`core.<tool_id>`）与**默认最小暴露**。
此前 `MCPServer` 的方法级行为齐备，却**没有任何事件循环**把它们接到 JSON-RPC 上
（`serve()` 只绑定连接即返回，CLI `mcp serve` 落「尚未接线」）⇒ 该场景在生产**不可达**；
且 `list_tools` 直接吐裸 `tool_id`（无命名空间前缀、未禁二级代理）。

本文件证明：① 事件循环按 `id` 应答、无 `id` 通知不应答、EOF 退出；② 单条请求异常被隔离为
错误应答且**循环继续**；③ 暴露面带 `core.` 前缀、`mcp.*` 远程工具**不**被二级代理暴露、
未暴露工具调用返回 `PERMISSION_DENIED`；④ **端到端**：用本仓**自己的 client**
（`StdioTransport`）拉起 `core-agent mcp serve` 子进程，完成握手 → 发现 → 调用 → 拒绝全链路。
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import sys
from typing import Any

import pytest

from core.entry import _build_parser, _mcp_serve, _mcp_whitelist
from core.mcp import MCPClient, MCPEndpoint, MCPServer
from core.mcp.server import PROTOCOL_VERSION
from core.plugin_registry import CoeffectResolver
from core.tools import Tool, ToolDef, ToolProvider

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

_METHOD_NOT_FOUND = -32601  # JSON-RPC 协议层「方法未实现」

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
    "  reasoning_effort: low\n"
)

# 子进程引导：以真实 CLI 入口起 server（stdout 只走 JSON-RPC，诊断走 stderr）。
_BOOTSTRAP = (
    "from core.entry import main\nraise SystemExit(main(['--config', {cfg!r}, 'mcp', 'serve']))\n"
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
            handler=lambda path: {"content": pathlib.Path(str(path)).read_text(encoding="utf-8")},
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
    # client 侧发现的远程工具（`mcp.*` 命名空间）—— 不得二级代理暴露
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="mcp.remote.echo",
                description="remote",
                schema={"type": "object"},
                coeffects=[],
                reversible=False,
            ),
            handler=lambda **kwargs: kwargs,
        )
    )
    return provider


def _stdio(session_id: str = "s1") -> MCPEndpoint:
    """服务端 stdio 端点：连接由事件循环按 endpoint 绑定。"""
    return MCPEndpoint(transport="stdio", session_id=session_id)


def _feed(server: MCPServer, *messages: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """把消息喂进事件循环（EOF 结束），返回（应答列表, stdout 原文）。"""
    stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
    stdout = io.StringIO()
    server.serve_stdio(_stdio(), stdin=stdin, stdout=stdout)
    raw = stdout.getvalue()
    return [json.loads(line) for line in raw.splitlines() if line.strip()], raw


def _req(rid: int, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}


# ---- ① 事件循环：按 id 应答 / 通知不应答 / EOF 退出 ----


def test_initialize_handshake_returns_protocol_version() -> None:
    """握手必须回 client 侧同一 protocolVersion（否则客户端判协议不匹配）。"""
    responses, _ = _feed(MCPServer(tool_provider=_provider()), _req(1, "initialize"))
    assert responses[0]["id"] == 1
    assert responses[0]["result"]["protocolVersion"] == PROTOCOL_VERSION


def test_tools_list_and_call_answered_by_id() -> None:
    """每条请求按各自 id 应答（顺序配对），读取流关闭后循环退出。"""
    requests = [
        _req(7, "tools/list"),
        _req(9, "tools/call", {"name": "core.tools.file_read", "arguments": {"path": "x"}}),
        _req(11, "ping"),
    ]
    responses, raw = _feed(MCPServer(tool_provider=_provider()), *requests)
    assert [r["id"] for r in responses] == [r["id"] for r in requests]
    assert raw.count("\n") == len(requests)  # 每行一条应答（stdout 只写 JSON-RPC 帧）


def test_notification_without_id_is_not_answered() -> None:
    """无 id 的通知（如 notifications/initialized）不应答。"""
    responses, _ = _feed(
        MCPServer(tool_provider=_provider()),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        _req(1, "tools/list"),
    )
    assert [r["id"] for r in responses] == [1]


def test_malformed_line_is_skipped_without_killing_loop() -> None:
    """非 JSON 行（stdout 混入日志等）跳过，后续请求照常处理。"""
    stdin = io.StringIO("not json\n" + json.dumps(_req(3, "tools/list")) + "\n")
    stdout = io.StringIO()
    MCPServer(tool_provider=_provider()).serve_stdio(_stdio(), stdin=stdin, stdout=stdout)
    responses = [json.loads(line) for line in stdout.getvalue().splitlines() if line.strip()]
    assert [r["id"] for r in responses] == [3]


# ---- ② 异常隔离 ----


def test_unknown_method_returns_jsonrpc_error_and_loop_continues() -> None:
    unknown = _req(1, "no/such/method")
    follow_up = _req(2, "tools/list")
    responses, _ = _feed(MCPServer(tool_provider=_provider()), unknown, follow_up)
    assert responses[0]["id"] == unknown["id"]
    assert responses[0]["error"]["code"] == _METHOD_NOT_FOUND
    assert responses[1]["id"] == follow_up["id"] and "result" in responses[1]  # 循环未被打断


def test_handler_exception_is_isolated() -> None:
    """工具提供者抛异常 → 该 id 以错误应答，循环继续（不拖垮会话）。"""

    class _Boom:
        def active_tools(self) -> list[ToolDef]:
            raise RuntimeError("boom")

    responses, _ = _feed(
        MCPServer(tool_provider=_Boom()),  # type: ignore[arg-type] — 故意注入故障提供者
        _req(1, "tools/list"),
        _req(2, "ping"),
    )
    assert responses[0]["id"] == 1 and "error" in responses[0]
    assert responses[1] == {"jsonrpc": "2.0", "id": 2, "result": {}}


# ---- ③ 暴露面：命名空间 / 最小暴露 / 白名单 / 禁二级代理 ----


def test_exposed_names_are_core_namespaced() -> None:
    responses, _ = _feed(MCPServer(tool_provider=_provider()), _req(1, "tools/list"))
    names = [t["name"] for t in responses[0]["result"]]
    assert names == ["core.tools.file_read"]  # 只读类默认暴露，且带 core. 前缀


def test_remote_tools_are_not_exposed_second_hand() -> None:
    """client 侧已发现的 `mcp.*` 远程工具不得再对外暴露（禁止二级代理递归挂载）。"""
    responses, _ = _feed(MCPServer(tool_provider=_provider()), _req(1, "tools/list"))
    names = [t["name"] for t in responses[0]["result"]]
    assert not any(name.startswith("core.mcp.") for name in names)


def test_whitelist_exposes_write_tool() -> None:
    server = MCPServer(tool_provider=_provider(), whitelist=["tools.file_write"])
    responses, _ = _feed(server, _req(1, "tools/list"))
    assert [t["name"] for t in responses[0]["result"]] == ["core.tools.file_write"]


def test_whitelist_accepts_namespaced_form() -> None:
    """白名单写 `core.` 前缀形式同等生效（否则用户照 `tools/list` 抄名字会静默不匹配）。"""
    server = MCPServer(tool_provider=_provider(), whitelist=["core.tools.file_write"])
    responses, _ = _feed(server, _req(1, "tools/list"))
    assert [t["name"] for t in responses[0]["result"]] == ["core.tools.file_write"]


def test_unexposed_tool_call_is_denied_and_not_executed() -> None:
    """未暴露工具的调用 → PERMISSION_DENIED（`call_tool` 亦拒绝裸名）。"""
    server = MCPServer(tool_provider=_provider())
    responses, _ = _feed(
        server,
        _req(1, "tools/call", {"name": "core.tools.file_write", "arguments": {}}),
        _req(2, "tools/call", {"name": "tools.file_read", "arguments": {"path": "x"}}),
    )
    for response in responses:
        assert response["result"]["ok"] is False
        assert response["result"]["code"] == "PERMISSION_DENIED"


# ---- ④ 端到端：本仓自己的 client 拉起 `mcp serve` 子进程 ----


@pytest.fixture
def serve_env(tmp_path, monkeypatch):
    """真实 CLI 入口所需的配置与状态目录（stdout 留给 JSON-RPC）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION, encoding="utf-8")
    return {"cfg": str(cfg), "state": str(tmp_path / "state")}


def test_whitelist_flag_is_parsed_as_csv() -> None:
    """CLI 面：`--whitelist` 逗号分隔 → 列表（空白项丢弃，前缀由 server 归一）。"""
    args = _build_parser().parse_args(
        ["mcp", "serve", "--whitelist", " core.tools.file_write , tools.file_patch "]
    )
    assert _mcp_whitelist(args.whitelist) == ["core.tools.file_write", "tools.file_patch"]
    assert _mcp_whitelist("") == []


def test_non_stdio_transport_is_refused(serve_env, capsys) -> None:
    """http 方向事件循环未接入 ⇒ 明确拒绝（不静默起一个空 server）。"""
    args = _build_parser().parse_args(
        ["--config", serve_env["cfg"], "mcp", "serve", "--transport", "http"]
    )
    assert _mcp_serve(args) == 1
    assert "待接入" in capsys.readouterr().err


def _serve_endpoint(cfg: str) -> MCPEndpoint:
    return MCPEndpoint(
        transport="stdio",
        command=sys.executable,
        args=["-c", _BOOTSTRAP.format(cfg=cfg)],
    )


def test_own_client_discovers_and_calls_own_server(serve_env, tmp_path) -> None:
    """端到端：握手 → 发现（`core.` 前缀、写工具不暴露）→ 调用（复用 ToolProvider.invoke）。"""
    target = tmp_path / "note.txt"
    target.write_text("hello-mcp", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(_SRC)}
    previous = {k: os.environ.get(k) for k in ("PYTHONPATH", "OPENAI_API_KEY", "CORE_STATE_DIR")}
    os.environ.update(env)
    client = MCPClient()
    try:
        handle = client.connect(_serve_endpoint(serve_env["cfg"]))
        try:
            names = {tool.name for tool in client.list_tools(handle)}
            assert "core.tools.file_read" in names
            assert "core.tools.file_write" not in names  # 默认最小暴露
            ok = client.call_tool(handle, "core.tools.file_read", {"path": str(target)})
            assert ok.data["ok"] is True
            assert ok.data["data"]["content"] == "hello-mcp"
            denied = client.call_tool(
                handle, "core.tools.file_write", {"path": "x", "content": "y"}
            )
            assert denied.data["code"] == "PERMISSION_DENIED"
        finally:
            client.close(handle)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
