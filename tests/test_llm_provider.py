"""llm-provider 单元测试（对齐规格场景 + M1 验收锚点）。

覆盖：错误归一化（伪造 HTTP 异常 → LLMError 层级）、错误码语义、
同步薄壳与异步等价、registry 依赖注入、异步真并发、stdlib provider 传输（注入假传输；
模型调用可靠性（重试/指数退避、超时、降级切备用模型、流式断流；change 0060 / 账本 E11①）。
"""

from __future__ import annotations

import asyncio
import http.client
import json
import threading
import time
import urllib.error
import warnings
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from unittest import mock

import pytest

from core.llm_provider import (
    Embedding,
    LLMAuthError,
    LLMChunk,
    LLMError,
    LLMNetworkError,
    LLMProvider,
    LLMProviderRegistry,
    LLMRateLimitedError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    Message,
    StdlibLLMProvider,
    TokenUsage,
    ToolCall,
    UnknownProviderError,
    map_http_error,
)

_DELAY = 0.1
_SERIAL_THRESHOLD = 0.18  # 串行两次 sleep ≈ 2*_DELAY，真并发应显著低于此值


def _resp(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
        finish_reason="stop",
        provider="stub",
        model="stub",
    )


class _StubProvider(LLMProvider):
    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        return _resp("ok")

    async def astream(self, request: LLMRequest):
        for chunk in ("a", "b"):
            yield LLMChunk(content=chunk)

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        return [Embedding(vector=[0.1, 0.2]) for _ in texts]


class _SlowProvider(_StubProvider):
    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        await asyncio.sleep(_DELAY)
        return _resp("ok")


# ---- 错误归一化 ----


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x", code, f"HTTP {code}", {}, None)


def test_map_http_error_normalizes() -> None:
    assert isinstance(map_http_error(_http_error(401)), LLMAuthError)
    assert isinstance(map_http_error(_http_error(403)), LLMAuthError)
    assert isinstance(map_http_error(_http_error(429)), LLMRateLimitedError)
    assert isinstance(map_http_error(_http_error(408)), LLMTimeoutError)
    assert type(map_http_error(_http_error(500))) is LLMError
    assert isinstance(map_http_error(TimeoutError()), LLMTimeoutError)
    assert isinstance(map_http_error(urllib.error.URLError("unreachable")), LLMNetworkError)
    # 连接池直连 http.client：连接层异常（无 urllib 包装）同口径归一为可重试的网络错误
    assert isinstance(map_http_error(http.client.RemoteDisconnected("")), LLMNetworkError)
    assert isinstance(map_http_error(ConnectionResetError("reset")), LLMNetworkError)
    assert type(map_http_error(ValueError("?"))) is LLMError


def test_llm_error_codes() -> None:
    assert LLMTimeoutError("x").code == "LLM_TIMEOUT"
    assert LLMRateLimitedError("x").code == "LLM_RATE_LIMITED"
    assert LLMAuthError("x").code == "LLM_AUTH"
    assert LLMNetworkError("x").code == "LLM_NETWORK"
    assert UnknownProviderError("x").code == "LLM_UNKNOWN_PROVIDER"


# ---- 同步薄壳与异步等价 ----


def test_sync_wrappers_equivalent() -> None:
    provider = _StubProvider()
    req = LLMRequest(messages=[Message("user", "hi")], model="stub")
    assert provider.completion(req).content == "ok"
    assert [c.content for c in provider.stream(req)] == ["a", "b"]
    assert [e.vector for e in provider.embedding(["x"])] == [[0.1, 0.2]]


def test_sync_wrappers_inside_running_loop() -> None:
    """运行中事件循环内调用三个薄壳：经工作线程桥接，不再抛嵌套 asyncio.run 错误。"""
    provider = _StubProvider()
    req = LLMRequest(messages=[Message("user", "hi")], model="stub")

    async def main() -> None:
        assert provider.completion(req).content == "ok"
        assert [c.content for c in provider.stream(req)] == ["a", "b"]
        assert [e.vector for e in provider.embedding(["x"])] == [[0.1, 0.2]]

    asyncio.run(main())


def test_sync_wrapper_runs_coroutine_in_worker_thread() -> None:
    """循环内桥接在**另一线程**的新事件循环执行（异步实现可安全用 asyncio.run）。"""
    thread_ids: list[int] = []

    class _RecordingProvider(_StubProvider):
        async def acompletion(self, request: LLMRequest) -> LLMResponse:
            thread_ids.append(threading.get_ident())
            return _resp("ok")

    provider = _RecordingProvider()
    req = LLMRequest(messages=[Message("user", "hi")], model="stub")

    async def main() -> int:
        provider.completion(req)
        return threading.get_ident()

    loop_thread = asyncio.run(main())
    assert thread_ids and thread_ids[0] != loop_thread


def test_sync_wrapper_propagates_llm_error_inside_loop() -> None:
    """循环内桥接透传归一化错误，且桥接失败不留下未等待协程（无 RuntimeWarning）。"""

    class _FailingProvider(_StubProvider):
        async def acompletion(self, request: LLMRequest) -> LLMResponse:
            raise LLMError("boom")

    provider = _FailingProvider()
    req = LLMRequest(messages=[Message("user", "hi")], model="stub")

    async def main() -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            with pytest.raises(LLMError):
                provider.completion(req)

    asyncio.run(main())


# ---- registry 依赖注入 ----


def test_registry_resolve_and_default() -> None:
    reg = LLMProviderRegistry()
    stub = _StubProvider()
    reg.register("stub", stub)
    assert reg.resolve("stub") is stub
    assert reg.resolve("stub/model-x") is stub
    with pytest.raises(UnknownProviderError):
        reg.resolve("unknown")
    assert isinstance(reg.default(), StdlibLLMProvider)


# ---- 异步真并发 ----


def test_async_true_concurrency() -> None:
    async def main() -> tuple[list[str], float]:
        provider = _SlowProvider()
        req = LLMRequest(messages=[Message("user", "hi")], model="m")
        start = time.perf_counter()
        results = await asyncio.gather(provider.acompletion(req), provider.acompletion(req))
        return [r.content for r in results], time.perf_counter() - start

    contents, elapsed = asyncio.run(main())
    assert contents == ["ok", "ok"]
    assert elapsed < _SERIAL_THRESHOLD


# ---- StdlibLLMProvider 传输（注入假传输，不发真实网络）----
# 连接复用（change 0066）后 provider 经 ``transport`` 接缝取响应，不再直接调 urlopen；
# 真实 socket 上的复用 / 重建见 ``tests/test_llm_provider_reuse.py``。


class _FakeTransport:
    """传输替身：记录请求并按序交出预置响应（替代 mock urlopen）。"""

    def __init__(self, *responses: Any) -> None:
        self._responses = list(responses)
        self.requests: list[Any] = []

    @contextmanager
    def send(self, request: Any, *, timeout: float) -> Generator[Any, None, None]:
        self.requests.append(request)
        yield self._responses[0] if len(self._responses) == 1 else self._responses.pop(0)

    @property
    def last(self) -> Any:
        return self.requests[-1]


def _make_provider(transport: Any = None) -> StdlibLLMProvider:
    return StdlibLLMProvider(
        api_key="k", base_url="https://example.com/v1", model="m", transport=transport
    )


def _fake_json_response(payload: dict) -> mock.MagicMock:
    resp = mock.MagicMock()
    resp.__enter__.return_value = resp
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    return resp


async def _collect_stream(provider: StdlibLLMProvider, request: LLMRequest) -> list[str]:
    return [chunk.content async for chunk in provider.astream(request)]


def test_acompletion_posts_openai_shape() -> None:
    payload = {
        "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3},
    }
    transport = _FakeTransport(_fake_json_response(payload))
    provider = _make_provider(transport)
    result = asyncio.run(
        provider.acompletion(LLMRequest(messages=[Message("user", "hi")], model="m"))
    )

    assert result.content == "hi"
    assert result.usage == TokenUsage(prompt_tokens=2, completion_tokens=3)
    req = transport.last
    assert req.full_url == "https://example.com/v1/chat/completions"
    body = json.loads(req.data.decode("utf-8"))
    assert body["model"] == "m"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert "reasoning_effort" not in body  # 未配置不下发（不支持该字段的端点零影响）


def test_reasoning_effort_passthrough() -> None:
    transport = _FakeTransport(
        _fake_json_response({"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]})
    )
    provider = _make_provider(transport)
    asyncio.run(
        provider.acompletion(
            LLMRequest(messages=[Message("user", "hi")], model="m", reasoning_effort="low")
        )
    )
    body = json.loads(transport.last.data.decode("utf-8"))
    assert body["reasoning_effort"] == "low"


def test_astream_parses_sse() -> None:
    lines = [
        b'data: {"choices":[{"delta":{"content":"he"}}]}\n',
        b"\n",
        b'data: {"choices":[{"delta":{"content":"llo"}}]}\n',
        b"data: [DONE]\n",
    ]
    transport = _FakeTransport(_stream_response(lines))
    provider = _make_provider(transport)
    chunks = asyncio.run(
        _collect_stream(provider, LLMRequest(messages=[Message("user", "hi")], model="m"))
    )

    assert chunks == ["he", "llo"]
    body = json.loads(transport.last.data.decode("utf-8"))
    assert body["stream"] is True


def test_astream_idle_timeout_raises_llm_timeout() -> None:
    """连接存活但无增量 ⇒ 等待上限归一为 LLMTimeoutError，已收增量保留（change 0256）。"""
    release = threading.Event()
    received: list[str] = []

    def _lines() -> Any:
        yield b'data: {"choices":[{"delta":{"content":"a"}}]}\n'
        release.wait(1)  # 模拟 SSE 注释 / keep-alive：连接活着但永不产出 data 帧

    provider = StdlibLLMProvider(
        api_key="k",
        base_url="https://example.com/v1",
        model="m",
        timeout=0.05,
        transport=_FakeTransport(_stream_response(_lines())),
    )

    async def _run() -> None:
        try:
            async for chunk in provider.astream(
                LLMRequest(messages=[Message("user", "hi")], model="m")
            ):
                received.append(chunk.content)  # noqa: PERF401 — 保序收集，便于断言
        finally:
            release.set()  # 放行生产者线程，避免 asyncio.run 关停执行器时等待

    started = time.monotonic()
    with pytest.raises(LLMTimeoutError):
        asyncio.run(_run())

    assert time.monotonic() - started < 2.0, "无增量等待必须有上限"  # noqa: PLR2004 — 断言阈值
    assert received == ["a"], "超时前已外发的增量保持已交付"


def test_astream_continuous_deltas_do_not_timeout() -> None:
    """增量持续到达（间隔远小于 timeout）⇒ 不误杀（change 0256）。"""

    def _lines() -> Any:
        for text in ("a", "b", "c"):
            yield f'data: {{"choices":[{{"delta":{{"content":"{text}"}}}}]}}\n'.encode()
            time.sleep(0.01)

    provider = StdlibLLMProvider(
        api_key="k",
        base_url="https://example.com/v1",
        model="m",
        timeout=2.0,
        transport=_FakeTransport(_stream_response(_lines())),
    )
    chunks = asyncio.run(
        _collect_stream(provider, LLMRequest(messages=[Message("user", "hi")], model="m"))
    )
    assert chunks == ["a", "b", "c"]


# ---- 推理原文归一（change 0145 / 账本 E56）----


def _completion(payload: dict) -> LLMResponse:
    provider = _make_provider(_FakeTransport(_fake_json_response(payload)))
    return asyncio.run(
        provider.acompletion(LLMRequest(messages=[Message("user", "hi")], model="m"))
    )


def _chunks(lines: list[bytes]) -> list[LLMChunk]:
    provider = _make_provider(_FakeTransport(_stream_response(lines)))

    async def _collect() -> list[LLMChunk]:
        return [
            chunk
            async for chunk in provider.astream(
                LLMRequest(messages=[Message("user", "hi")], model="m")
            )
        ]

    return asyncio.run(_collect())


def _sse_lines(*payloads: str) -> list[bytes]:
    """把 JSON 载荷串编成 SSE `data:` 行（UTF-8 字节）并以 `[DONE]` 收尾。"""
    return [f"data: {payload}\n".encode() for payload in payloads] + [b"data: [DONE]\n"]


def test_response_maps_thinking_from_reasoning_content() -> None:
    """非流式：`message.reasoning_content` 归一为 `thinking`（与正文分属两字段，互不拼接）。"""
    result = _completion(
        {
            "choices": [
                {
                    "message": {"content": "答案 42", "reasoning_content": "先算 6×7"},
                    "finish_reason": "stop",
                }
            ]
        }
    )
    assert result.thinking == "先算 6×7"
    assert result.content == "答案 42"


def test_response_maps_thinking_from_openai_reasoning() -> None:
    """OpenAI 兼容口径 `reasoning`：同归一为 `thinking`（两家既有口径并存）。"""
    result = _completion(
        {
            "choices": [
                {"message": {"content": "答案", "reasoning": "推理全文"}, "finish_reason": "stop"}
            ]
        }
    )
    assert result.thinking == "推理全文"


def test_chunk_maps_thinking_delta() -> None:
    """流式：`delta.reasoning_content` 逐段归一为 `thinking`，`content` 逐字不受影响。"""
    chunks = _chunks(
        _sse_lines(
            '{"choices":[{"delta":{"reasoning_content":"想"}}]}',
            '{"choices":[{"delta":{"reasoning_content":"一下"}}]}',
            '{"choices":[{"delta":{"content":"好"}}]}',
        )
    )
    assert [c.thinking for c in chunks] == ["想", "一下", ""]
    assert [c.content for c in chunks] == ["", "", "好"]


def test_thinking_empty_when_absent() -> None:
    """端点未返回推理字段 ⇒ `thinking` 为空串，既有字段解析逐字不变（零回归）。"""
    response = _completion({"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]})
    assert response.thinking == ""
    assert response.content == "hi"
    assert (
        _chunks([b'data: {"choices":[{"delta":{"content":"x"}}]}\n', b"data: [DONE]\n"])[0].thinking
        == ""
    )


def test_chunk_maps_finish_reason() -> None:
    """流式增量携带终止原因（change 0170）：末块 `length` ⇒ 字段为 `length`；缺失 ⇒ 空串。"""
    chunks = _chunks(
        _sse_lines(
            '{"choices":[{"delta":{"content":"甲"}}]}',
            '{"choices":[{"delta":{},"finish_reason":"length"}]}',
        )
    )
    assert [c.finish_reason for c in chunks] == ["", "length"]
    assert [c.content for c in chunks] == ["甲", ""]  # 其余字段逐字不受影响
    assert chunks[0].thinking == "" and chunks[0].tool_calls is None


# ---- 流式令牌用量与请求侧输出上限（change 0183 / ADR-0174 / 账本 E120）----


def test_chunk_maps_usage_from_empty_choices_end_block() -> None:
    """流式末块 `choices` 为空数组但顶层带 `usage` ⇒ **仍**产出用量块（不因 choices 空而丢弃）。"""
    chunks = _chunks(
        _sse_lines(
            '{"choices":[{"delta":{"content":"甲"}}]}',
            '{"choices":[],"usage":{"prompt_tokens":120,"completion_tokens":34}}',
        )
    )
    assert [c.usage for c in chunks] == [None, TokenUsage(prompt_tokens=120, completion_tokens=34)]
    assert [c.content for c in chunks] == ["甲", ""]  # 其余字段逐字不受影响


def test_chunk_usage_none_when_absent() -> None:
    """未携带用量（无 `usage` 键 / 值为 `null`）⇒ `usage` 为 `None`（不报错、不以零值冒充）。"""
    chunks = _chunks(
        _sse_lines(
            '{"choices":[{"delta":{"content":"甲"}}]}',
            '{"choices":[{"delta":{"content":"乙"}}],"usage":null}',
        )
    )
    assert [c.usage for c in chunks] == [None, None]
    assert [c.content for c in chunks] == ["甲", "乙"]


def test_stream_body_requests_include_usage() -> None:
    """流式请求体要求端点上报用量（`stream_options.include_usage`），`stream` 与既有形状不变。"""
    lines = [b'data: {"choices":[{"delta":{"content":"x"}}]}\n', b"data: [DONE]\n"]
    transport = _FakeTransport(_stream_response(lines))
    provider = _make_provider(transport)
    asyncio.run(_collect_stream(provider, LLMRequest(messages=[Message("user", "hi")], model="m")))

    body = json.loads(transport.last.data.decode("utf-8"))
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}


def test_body_omits_stream_options_when_non_streaming() -> None:
    """非流式请求体**不含** `stream_options`（其响应本就携带 `usage`；既有形状逐字保留）。"""
    payload = {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
    transport = _FakeTransport(_fake_json_response(payload))
    provider = _make_provider(transport)
    asyncio.run(provider.acompletion(LLMRequest(messages=[Message("user", "hi")], model="m")))

    body = json.loads(transport.last.data.decode("utf-8"))
    assert "stream_options" not in body
    assert "stream" not in body


def test_response_maps_native_tool_calls() -> None:
    """非流式：message.tool_calls 归一为 ToolCall（原生 function call 协议）。"""
    provider = _make_provider()
    payload = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "tools.echo", "arguments": '{"text": "hi"}'},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
    }
    transport = _FakeTransport(_fake_json_response(payload))
    provider = _make_provider(transport)
    result = asyncio.run(
        provider.acompletion(LLMRequest(messages=[Message("user", "hi")], model="m"))
    )
    assert result.tool_calls == [
        ToolCall(tool_id="tools.echo", arguments='{"text": "hi"}', call_id="call_1", index=0)
    ]


def test_astream_maps_tool_call_fragments() -> None:
    """流式：delta.tool_calls 增量片段透传（index 分组、arguments 为增量段）。"""
    provider = _make_provider()
    lines = [
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1",'
        b'"function":{"name":"tools.echo","arguments":""}}]}}]}\n',
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        b'"function":{"arguments":"{\\"text\\":"}}]}}]}\n',
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        b'"function":{"arguments":" \\"hi\\"}"}}]}}]}\n',
        b"data: [DONE]\n",
    ]
    provider = _make_provider(_FakeTransport(_stream_response(lines)))

    async def _collect_chunks() -> list[LLMChunk]:
        return [
            chunk
            async for chunk in provider.astream(
                LLMRequest(messages=[Message("user", "hi")], model="m")
            )
        ]

    chunks = asyncio.run(_collect_chunks())
    fragments = [c for c in chunks if c.tool_calls]
    assert [c.content for c in chunks if c.content] == []
    assert fragments[0].tool_calls == [
        ToolCall(tool_id="tools.echo", arguments="", call_id="c1", index=0)
    ]
    assert fragments[1].tool_calls == [ToolCall(tool_id="", arguments='{"text":', index=0)]
    assert fragments[2].tool_calls == [ToolCall(tool_id="", arguments=' "hi"}', index=0)]


def test_aembedding_maps() -> None:
    transport = _FakeTransport(_fake_json_response({"data": [{"embedding": [0.1, 0.2]}]}))
    provider = _make_provider(transport)
    embeddings = asyncio.run(provider.aembedding(["x"]))

    assert embeddings[0].vector == [0.1, 0.2]
    assert transport.last.full_url == "https://example.com/v1/embeddings"


# ---- 模型调用可靠性（change 0060 / 账本 E11①）----
# 规格「模型调用可靠性」四场景：失败自动重试（指数退避）/ 超时控制 / 服务降级（切备用模型）/
# 流式断流。此前只有实现、无任何用例（账本 E11①）。

_REQ = LLMRequest(messages=[Message("user", "hi")], model="primary")
_RETRIES = 2  # 重试上限（总调用次数 = 初次 + _RETRIES）
_BACKOFF_CAP = 8.0  # 退避封顶（秒）
_TIMEOUT = 0.05  # 极短超时（用例用）


def _reliable(**kw: Any) -> StdlibLLMProvider:
    return StdlibLLMProvider(api_key="k", base_url="https://example.com/v1", model="m", **kw)


def _no_sleep(provider: StdlibLLMProvider) -> mock.MagicMock:
    """退避置零（用例只关心重试次数，不真等 0.5/1/2s）。"""
    return mock.patch.object(provider, "_backoff", lambda attempt: 0.0)


def test_backoff_is_exponential_and_capped() -> None:
    provider = _reliable()
    assert [provider._backoff(n) for n in (1, 2, 3, 4)] == [0.5, 1.0, 2.0, 4.0]  # noqa: SLF001
    assert provider._backoff(10) == _BACKOFF_CAP  # noqa: SLF001 — 封顶


def test_acompletion_retries_until_success() -> None:
    """可重试错误按退避重试，成功即返回。"""
    provider = _reliable(max_retries=_RETRIES)
    calls = {"n": 0}

    async def _flaky(request: LLMRequest, model: str) -> LLMResponse:
        calls["n"] += 1
        if calls["n"] <= _RETRIES:  # 前 _RETRIES 次抖动
            raise LLMNetworkError("网络抖动")
        return _resp("ok")

    with mock.patch.object(provider, "_call_provider", _flaky), _no_sleep(provider):
        result = asyncio.run(provider.acompletion(_REQ))
    assert result.content == "ok"
    assert calls["n"] == _RETRIES + 1  # 初次 + 重试


def test_retry_exhausted_raises_normalized_error() -> None:
    """达到最大重试次数仍失败：抛归一化异常（不泄漏底层）。"""
    provider = _reliable(max_retries=_RETRIES)
    calls = {"n": 0}

    async def _always_429(request: LLMRequest, model: str) -> LLMResponse:
        calls["n"] += 1
        raise LLMRateLimitedError("限流")

    with (
        mock.patch.object(provider, "_call_provider", _always_429),
        _no_sleep(provider),
        pytest.raises(LLMRateLimitedError),
    ):
        asyncio.run(provider.acompletion(_REQ))
    assert calls["n"] == _RETRIES + 1  # 初次 + max_retries


def test_non_retryable_error_is_not_retried() -> None:
    """鉴权等非瞬时错误：立即抛出，不做无谓重试。"""
    provider = _reliable(max_retries=3)
    calls = {"n": 0}

    async def _auth(request: LLMRequest, model: str) -> LLMResponse:
        calls["n"] += 1
        raise LLMAuthError("401")

    with (
        mock.patch.object(provider, "_call_provider", _auth),
        _no_sleep(provider),
        pytest.raises(LLMAuthError),
    ):
        asyncio.run(provider.acompletion(_REQ))
    assert calls["n"] == 1


def test_call_timeout_is_enforced() -> None:
    """超时：取消等待并抛 LLMTimeoutError，不随被调用一起挂起。"""
    provider = _reliable(timeout=_TIMEOUT, max_retries=0)

    async def _hang(request: LLMRequest, model: str) -> LLMResponse:
        await asyncio.sleep(1.0)
        return _resp("ok")

    with mock.patch.object(provider, "_call_provider", _hang):
        start = time.perf_counter()
        with pytest.raises(LLMTimeoutError):
            asyncio.run(provider.acompletion(_REQ))
        elapsed = time.perf_counter() - start
    assert elapsed < 1.0  # 未等待慢调用自然结束


def test_degrades_to_fallback_model() -> None:
    """服务降级：主模型不可用 → 切备用模型，成功则留痕。"""
    seen: list[str] = []
    audits: list[str] = []
    provider = _reliable(
        max_retries=0, fallback_models=["backup"], audit=lambda m, r: audits.append(m)
    )

    async def _primary_down(request: LLMRequest, model: str) -> LLMResponse:
        seen.append(model)
        if model == "primary":
            raise LLMNetworkError("主模型不可用")
        return _resp("backup ok")

    with mock.patch.object(provider, "_call_provider", _primary_down):
        result = asyncio.run(provider.acompletion(_REQ))
    assert seen == ["primary", "backup"]
    assert result.content == "backup ok"
    assert audits == ["backup"]  # 审计记的是实际成功的模型


def test_non_retryable_error_does_not_fall_back() -> None:
    """非瞬时错误不触发降级（换模型也救不了，不浪费一次调用）。"""
    seen: list[str] = []
    provider = _reliable(max_retries=0, fallback_models=["backup"])

    async def _auth(request: LLMRequest, model: str) -> LLMResponse:
        seen.append(model)
        raise LLMAuthError("401")

    with mock.patch.object(provider, "_call_provider", _auth), pytest.raises(LLMAuthError):
        asyncio.run(provider.acompletion(_REQ))
    assert seen == ["primary"]


def _stream_response(lines: Any) -> mock.MagicMock:
    """lines 为可迭代对象（列表或惰性生成器——后者用于在中途抛断流）。"""
    resp = mock.MagicMock()
    resp.__enter__.return_value = resp
    resp.__iter__.return_value = iter(lines)
    return resp


def test_stream_without_done_marker_returns_partial() -> None:
    """断流（无 [DONE] 提前结束）：已接收内容部分返回，调用方不挂起。"""
    lines = [
        b'data: {"choices":[{"delta":{"content":"a"}}]}\n',
        b'data: {"choices":[{"delta":{"content":"b"}}]}\n',
    ]
    provider = _make_provider(_FakeTransport(_stream_response(lines)))
    chunks = asyncio.run(
        _collect_stream(provider, LLMRequest(messages=[Message("user", "hi")], model="m"))
    )
    assert chunks == ["a", "b"]


def test_stream_mid_transport_error_surfaces_partial_then_raises() -> None:
    """断流（传输中途异常）：先返回已收内容，再抛归一化错误，绝不无限挂起。"""

    def _lines() -> Any:
        yield b'data: {"choices":[{"delta":{"content":"a"}}]}\n'
        raise urllib.error.URLError("连接被切断")

    provider = _make_provider(_FakeTransport(_stream_response(_lines())))
    got: list[str] = []

    async def _run() -> None:
        request = LLMRequest(messages=[Message("user", "hi")], model="m")
        async for chunk in provider.astream(request):
            got.append(chunk.content)  # noqa: PERF401 — 断流时须保留已收部分，推导式会丢

    with pytest.raises(LLMNetworkError):
        asyncio.run(_run())
    assert got == ["a"]


# ---- provider 审计标签（change 0184 / ADR-0175 / 账本 E121）----
# 规格「模型调用审计」：`LLMResponse.provider` 须反映**实际使用的 provider 标识**，
# 由组合根按 `llm.provider` 构造期注入；未注入时回落实现自身身份（"stdlib"）。
# 此前 `_map_response` 硬编码 `"stdlib"` ⇒ 配置面写什么都没用（死标签）。


def test_response_provider_label_reflects_configuration() -> None:
    """注入 provider 名 ⇒ 响应标签即为该名（配置面所见 = 响应面所见）。"""
    payload = {
        "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    provider = StdlibLLMProvider(
        api_key="k",
        base_url="https://example.com/v1",
        model="m",
        provider="litellm",
        transport=_FakeTransport(_fake_json_response(payload)),
    )
    result = asyncio.run(
        provider.acompletion(LLMRequest(messages=[Message("user", "hi")], model="m"))
    )

    assert result.provider == "litellm"


def test_response_provider_defaults_to_identity() -> None:
    """未注入 provider（裸构造 / 测试替身）⇒ 回落实现自身身份，与既有行为**逐字一致**。"""
    payload = {
        "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    provider = _make_provider(_FakeTransport(_fake_json_response(payload)))
    result = asyncio.run(
        provider.acompletion(LLMRequest(messages=[Message("user", "hi")], model="m"))
    )

    assert result.provider == "stdlib"


def test_response_provider_blank_falls_back_to_identity() -> None:
    """空串（配置面不该出现，但接口面必须自守）⇒ 不把空标签写进审计。"""
    payload = {
        "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    provider = StdlibLLMProvider(
        api_key="k",
        base_url="https://example.com/v1",
        model="m",
        provider="",
        transport=_FakeTransport(_fake_json_response(payload)),
    )
    result = asyncio.run(
        provider.acompletion(LLMRequest(messages=[Message("user", "hi")], model="m"))
    )

    assert result.provider == "stdlib"
