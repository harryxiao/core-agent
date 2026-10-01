"""llm-provider 单元测试（对齐规格场景 + M1 验收锚点）。

覆盖：错误归一化（伪造 HTTP 异常 → LLMError 层级）、错误码语义、
同步薄壳与异步等价、registry 依赖注入、异步真并发、stdlib provider 传输（mock urlopen）。
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.error
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


# ---- StdlibLLMProvider 传输（mock urlopen，不发真实网络）----


def _make_provider() -> StdlibLLMProvider:
    return StdlibLLMProvider(api_key="k", base_url="https://example.com/v1", model="m")


def _fake_json_response(payload: dict) -> mock.MagicMock:
    resp = mock.MagicMock()
    resp.__enter__.return_value = resp
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    return resp


async def _collect_stream(provider: StdlibLLMProvider, request: LLMRequest) -> list[str]:
    return [chunk.content async for chunk in provider.astream(request)]


def test_acompletion_posts_openai_shape() -> None:
    provider = _make_provider()
    payload = {
        "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3},
    }
    resp = _fake_json_response(payload)
    with mock.patch(
        "core.llm_provider.stdlib_provider.urllib.request.urlopen", return_value=resp
    ) as urlopen:
        result = asyncio.run(
            provider.acompletion(LLMRequest(messages=[Message("user", "hi")], model="m"))
        )

    assert result.content == "hi"
    assert result.usage == TokenUsage(prompt_tokens=2, completion_tokens=3)
    req = urlopen.call_args[0][0]
    assert req.full_url == "https://example.com/v1/chat/completions"
    body = json.loads(req.data.decode("utf-8"))
    assert body["model"] == "m"
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_astream_parses_sse() -> None:
    provider = _make_provider()
    lines = [
        b'data: {"choices":[{"delta":{"content":"he"}}]}\n',
        b"\n",
        b'data: {"choices":[{"delta":{"content":"llo"}}]}\n',
        b"data: [DONE]\n",
    ]
    resp = mock.MagicMock()
    resp.__enter__.return_value = resp
    resp.__iter__.return_value = iter(lines)
    with mock.patch(
        "core.llm_provider.stdlib_provider.urllib.request.urlopen", return_value=resp
    ) as urlopen:
        chunks = asyncio.run(
            _collect_stream(provider, LLMRequest(messages=[Message("user", "hi")], model="m"))
        )

    assert chunks == ["he", "llo"]
    body = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))
    assert body["stream"] is True


def test_aembedding_maps() -> None:
    provider = _make_provider()
    resp = _fake_json_response({"data": [{"embedding": [0.1, 0.2]}]})
    with mock.patch(
        "core.llm_provider.stdlib_provider.urllib.request.urlopen", return_value=resp
    ) as urlopen:
        embeddings = asyncio.run(provider.aembedding(["x"]))

    assert embeddings[0].vector == [0.1, 0.2]
    assert urlopen.call_args[0][0].full_url == "https://example.com/v1/embeddings"
