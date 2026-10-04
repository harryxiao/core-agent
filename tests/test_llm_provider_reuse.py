"""stdlib provider 连接复用与失效重建（change 0066 / 账本 E11②）。

规格 llm-provider「模型调用可靠性」场景「连接复用」：「复用底层 connection / keep-alive
连接，减少握手开销，**连接失效时自动重建**」。

既有 `tests/test_llm_provider.py` 用 **mock urlopen** 覆盖协议映射（不发真实网络），
覆盖不到「连接本身」；本文件补那一半：本地 `http.server` 桩统计**服务端接受的连接数**，
把规格场景变成可断言的事实 —— 复用 ⇒ 两次调用只 accept 一条连接；失效 ⇒ 自动重建后调用仍成功。
"""

from __future__ import annotations

import asyncio
import json
import threading
import urllib.request
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from unittest import mock

import pytest

from core.llm_provider import (
    LLMNetworkError,
    LLMRateLimitedError,
    LLMRequest,
    Message,
    StdlibLLMProvider,
)
from core.llm_provider.http_pool import HTTPConnectionPool

_OK = 200
_ONE_CONNECTION = 1  # 复用：两次调用共用一条连接
_TWO_CALLS = 2  # 两次调用（请求数）
_REBUILT_CONNECTION = 2  # 失效重建：旧连接关掉后新建一条
_REQUEST = LLMRequest(messages=[Message("user", "hi")], model="m")
_CHAT = {
    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
}
_SSE = b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n'


class _StubHandler(BaseHTTPRequestHandler):
    """最小 OpenAI 兼容桩：按路径应答 chat / embeddings / SSE，并按连接计数。"""

    protocol_version = "HTTP/1.1"  # 关键：HTTP/1.1 才谈得上 keep-alive
    connections = 0  # 服务端已接受的连接数（每条 TCP 连接一次 setup）
    requests = 0  # 已处理请求数
    close_after_first = False  # 模拟服务端空闲超时：答完首请求即悄悄关连接
    status = 200  # 非 200：直接回该状态码（走 HTTPError 归一）

    def setup(self) -> None:
        super().setup()
        type(self).connections += 1

    def log_message(self, *args: Any) -> None:
        """静默：桩不需要访问日志。"""

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler 约定
        cls = type(self)
        cls.requests += 1
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if cls.status != _OK:
            self._send(cls.status, b'{"error": "boom"}', "application/json")
        elif "/stream/" in self.path:
            self._send(_OK, _SSE, "text/event-stream")
        elif self.path.endswith("/embeddings"):
            body = json.dumps({"data": [{"embedding": [0.1, 0.2]}]}).encode()
            self._send(_OK, body, "application/json")
        else:
            self._send(_OK, json.dumps(_CHAT).encode(), "application/json")
        if cls.close_after_first:
            self.close_connection = True  # 不发 Connection: close，模拟服务端静默关闭

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@contextmanager
def _serve(**attrs: Any) -> Iterator[tuple[Any, str]]:
    """起一个本地桩服务（端口随机），产出 (handler 类, base_url)。"""
    handler = type("_Stub", (_StubHandler,), {"connections": 0, "requests": 0, **attrs})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield handler, f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(autouse=True)
def _direct(monkeypatch: pytest.MonkeyPatch) -> None:
    """置空环境代理探测：本地桩要求直连（代理回落另有专门用例）。"""
    monkeypatch.setattr("core.llm_provider.http_pool.proxy_for", lambda url: None)


def _provider(base_url: str, **kw: Any) -> StdlibLLMProvider:
    return StdlibLLMProvider(
        api_key="k", base_url=base_url, model="m", timeout=5.0, max_retries=0, **kw
    )


def _in_one_thread(coro: Any) -> Any:
    """在**单工作线程**的事件循环里跑：provider 的同步调用经线程池落到同一线程，
    线程本地连接池的复用因此可确定断言（不依赖线程池调度）。"""
    loop = asyncio.new_event_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(executor)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        executor.shutdown(wait=True)


# ---- 复用（规格场景「连接复用」）----


def test_two_calls_reuse_one_connection() -> None:
    """同一线程连续两次调用共用一条 keep-alive 连接（服务端只 accept 一次）。"""
    with _serve() as (handler, base):
        provider = _provider(base)

        async def _twice() -> list[str]:
            first = await provider.acompletion(_REQUEST)
            second = await provider.acompletion(_REQUEST)
            return [first.content, second.content]

        assert _in_one_thread(_twice()) == ["ok", "ok"]
        assert handler.requests == _TWO_CALLS  # 两次请求都到达
        assert handler.connections == _ONE_CONNECTION  # ← 关键：只握手一次


def test_embedding_shares_the_same_connection() -> None:
    """复用覆盖 embeddings 路径（RAG 索引循环是主要收益方）。"""
    with _serve() as (handler, base):
        provider = _provider(base)

        async def _both() -> None:
            await provider.acompletion(_REQUEST)
            await provider.aembedding(["x"])

        _in_one_thread(_both())
        assert handler.connections == _ONE_CONNECTION


def test_pool_keys_connections_by_origin() -> None:
    """同一个池内按 origin 分键：两个 host 各一条，互不串用；回到首个 origin 仍复用。"""
    with _serve() as (first, base_first), _serve() as (second, base_second):
        pool = HTTPConnectionPool()

        def _post(base: str) -> None:
            req = urllib.request.Request(
                f"{base}/chat/completions",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with pool.send(req, timeout=5.0) as resp:
                resp.read()

        _post(base_first)
        _post(base_second)
        _post(base_first)  # 回到首个 origin：仍复用其既有连接
        assert (first.connections, second.connections) == (_ONE_CONNECTION, _ONE_CONNECTION)


# ---- 失效自动重建（规格场景「连接失效时自动重建」）----


def test_connection_rebuilt_after_server_side_close() -> None:
    """服务端关闭空闲连接后，下一次调用自动重建连接并成功（不向调用方抛错）。"""
    with _serve(close_after_first=True) as (handler, base):
        provider = _provider(base)

        async def _twice() -> list[str]:
            first = await provider.acompletion(_REQUEST)
            second = await provider.acompletion(_REQUEST)
            return [first.content, second.content]

        assert _in_one_thread(_twice()) == ["ok", "ok"]
        assert handler.connections == _REBUILT_CONNECTION  # 旧连接失效 ⇒ 自动重建一次


# ---- 错误归一（http.client 路径同样不泄漏底层异常）----


def test_error_status_maps_to_domain_error() -> None:
    """4xx 仍归一为领域异常：429 → LLMRateLimitedError（与 urlopen 路径同口径）。"""
    with _serve(status=429) as (_handler, base), pytest.raises(LLMRateLimitedError):
        _in_one_thread(_provider(base).acompletion(_REQUEST))


def test_connection_failure_maps_to_network_error() -> None:
    """连接层失败（拒绝连接）归一为 LLMNetworkError（可重试），不落裸 OSError。"""
    provider = _provider("http://127.0.0.1:1/v1")  # 端口 1：本地必被拒绝
    with pytest.raises(LLMNetworkError):
        _in_one_thread(provider.acompletion(_REQUEST))


# ---- 回落与流式 ----


def test_redirect_falls_back_to_urlopen() -> None:
    """3xx 交回 urlopen（http.client 自身不跟随重定向）。"""
    seen: list[Any] = []

    def _fake_urlopen(req: Any, timeout: Any = None) -> Any:
        seen.append(req)
        return _json_cm(_CHAT)

    with (
        _serve(status=302) as (_handler, base),
        mock.patch("urllib.request.urlopen", _fake_urlopen),
    ):
        result = _in_one_thread(_provider(base).acompletion(_REQUEST))
    assert result.content == "ok"
    assert [req.full_url for req in seen] == [f"{base}/chat/completions"]  # 回落确实发生


def test_proxy_configured_falls_back_to_urlopen(monkeypatch: pytest.MonkeyPatch) -> None:
    """配置了代理的环境不进池，交回 urlopen（保留 stdlib 代理语义）。"""
    seen: list[Any] = []

    def _fake_urlopen(req: Any, timeout: Any = None) -> Any:
        seen.append(req)
        return _json_cm(_CHAT)

    monkeypatch.setattr(
        "core.llm_provider.http_pool.proxy_for", lambda url: "http://proxy.invalid:8080"
    )
    with mock.patch("urllib.request.urlopen", _fake_urlopen):
        result = _in_one_thread(_provider("http://127.0.0.1:9/v1").acompletion(_REQUEST))
    assert result.content == "ok"
    assert len(seen) == 1  # 走代理路径，未经连接池


def test_stream_completes_over_transport() -> None:
    """SSE 流式走同一传输层：内容正确；流未读尽 ⇒ 连接不复用（不污染下次请求）。"""
    with _serve() as (handler, base):
        # base 以 /stream 结尾 ⇒ 桩按 SSE 应答（路径为 /stream/chat/completions）
        provider = _provider(base.replace("/v1", "/stream"))

        async def _collect() -> list[str]:
            request = LLMRequest(messages=[Message("user", "hi")], model="m")
            return [chunk.content async for chunk in provider.astream(request)]

        assert _in_one_thread(_collect()) == ["hi"]
        assert handler.connections == _ONE_CONNECTION


def _json_cm(payload: dict[str, Any]) -> Any:
    """构造一个「上下文管理器式」的假响应（与既有 mock urlopen 测试同形）。"""
    resp = mock.MagicMock()
    resp.__enter__.return_value = resp
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    return resp
