"""llm-provider 单元测试（对齐规格场景 + M1 验收锚点）。

覆盖：错误归一化（伪造 litellm 异常 → LLMError 层级）、错误码语义、
同步薄壳与异步等价、registry 依赖注入、异步真并发。
"""

from __future__ import annotations

import asyncio
import time

import pytest

from core.llm_provider import (
    Embedding,
    LiteLLMProvider,
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
    TokenUsage,
    UnknownProviderError,
    map_litellm_error,
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


class _TimeoutError(Exception):
    status_code = 0


class _RateLimitError(Exception):
    status_code = 429


class _AuthError(Exception):
    status_code = 401


class _APIConnectionError(Exception):
    status_code = 0


class _UnknownError(Exception):
    status_code = 0


def test_map_litellm_error_normalizes() -> None:
    assert isinstance(map_litellm_error(_TimeoutError()), LLMTimeoutError)
    assert isinstance(map_litellm_error(_RateLimitError()), LLMRateLimitedError)
    assert isinstance(map_litellm_error(_AuthError()), LLMAuthError)
    assert isinstance(map_litellm_error(_APIConnectionError()), LLMNetworkError)
    assert type(map_litellm_error(_UnknownError())) is LLMError


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
    assert isinstance(reg.default(), LiteLLMProvider)


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
