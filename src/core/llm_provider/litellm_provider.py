"""LiteLLM 默认实现与错误归一化（llm-provider）。

LiteLLM 在调用时懒加载（离线环境不阻塞模块导入），底层供应商异常统一经
``map_litellm_error`` 归一到 ``LLMError`` 层级；调用路径内置指数退避重试、
超时控制与降级切换备用模型；API Key / URL 配置即路由，无需逐家适配。

对应接口：doc/03-interfaces/llm-provider-interface.md §3 / §5
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

from .errors import (
    LLMAuthError,
    LLMError,
    LLMNetworkError,
    LLMRateLimitedError,
    LLMTimeoutError,
    UnknownProviderError,
)
from .models import Embedding, LLMChunk, LLMRequest, LLMResponse, TokenUsage
from .provider import LLMProvider

# 可重试错误：限流 / 网络抖动 / 超时（鉴权等非瞬时错误不重试）
_RETRYABLE = (LLMRateLimitedError, LLMNetworkError, LLMTimeoutError)

# 底层供应商 HTTP 状态码 → 领域异常映射依据
_HTTP_TIMEOUT_CODES = (408, 504)
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_UNAUTHORIZED_CODES = (401, 403)


def _load_litellm() -> Any:
    """懒加载 litellm；未安装时归一为领域异常（默认实现无法离线运行）。"""
    try:
        return importlib.import_module("litellm")
    except ImportError as exc:
        raise UnknownProviderError("litellm 未安装，无法作为默认 provider") from exc  # noqa: TRY003


def map_litellm_error(exc: Exception) -> LLMError:
    """把 litellm / 底层供应商异常归一为领域异常（不泄漏原始异常结构）。"""
    name = type(exc).__name__.lower()
    status = int(getattr(exc, "status_code", 0) or 0)
    if "timeout" in name or status in _HTTP_TIMEOUT_CODES:
        return LLMTimeoutError(str(exc))
    if "ratelimit" in name or "rate_limit" in name or status == _HTTP_TOO_MANY_REQUESTS:
        return LLMRateLimitedError(str(exc))
    if "auth" in name or "authentication" in name or status in _HTTP_UNAUTHORIZED_CODES:
        return LLMAuthError(str(exc))
    if "connection" in name or "network" in name or "apiconnection" in name:
        return LLMNetworkError(str(exc))
    return LLMError(str(exc))


class LiteLLMProvider(LLMProvider):
    """默认实现：委托 LiteLLM 统一 100+ 模型协议。"""

    def __init__(  # noqa: PLR0913 — 可选配置参数多，构造注入
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        fallback_models: list[str] | None = None,
        audit: Callable[[str, LLMResponse], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries
        self._fallback = fallback_models if fallback_models is not None else []
        self._audit = audit

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        models = [request.model, *self._fallback]
        last: LLMError | None = None
        for model in models:
            try:
                response = await self._completion_with_retry(request, model)
            except LLMError as exc:
                last = exc
                if not isinstance(exc, _RETRYABLE):
                    break
                continue
            if self._audit is not None:
                self._audit(model, response)
            return response
        if last is None:
            last = UnknownProviderError(f"无可用 provider/model：{request.model}")  # noqa: TRY003
        raise last

    async def _completion_with_retry(self, request: LLMRequest, model: str) -> LLMResponse:
        last_error: LLMError | None = None
        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                await asyncio.sleep(self._backoff(attempt))
            try:
                return await asyncio.wait_for(
                    self._call_litellm(request, model), timeout=self._timeout
                )
            except TimeoutError as exc:
                last_error = LLMTimeoutError(f"调用超时（>{self._timeout}s）：{model}")
                last_error.__cause__ = exc
            except LLMError as exc:
                last_error = exc
                if not isinstance(exc, _RETRYABLE) or attempt >= self._max_retries:
                    raise
        assert last_error is not None
        raise last_error

    async def _call_litellm(self, request: LLMRequest, model: str) -> LLMResponse:
        litellm = _load_litellm()
        try:
            raw = await litellm.acompletion(**self._build_kwargs(request, model))
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 — 底层供应商异常统一归一
            raise map_litellm_error(exc) from exc
        return self._map_response(raw, model)

    async def astream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        litellm = _load_litellm()
        try:
            response = await litellm.acompletion(
                stream=True, **self._build_kwargs(request, request.model)
            )
            async for part in response:
                yield self._map_chunk(part)
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 — 断流 / 底层异常统一归一
            raise map_litellm_error(exc) from exc

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        if self._model is None:
            raise UnknownProviderError("embedding 需在构造时指定 model")  # noqa: TRY003
        litellm = _load_litellm()
        kwargs: dict[str, Any] = {"model": self._model, "input": texts}
        if self._api_key is not None:
            kwargs["api_key"] = self._api_key
        if self._base_url is not None:
            kwargs["api_base"] = self._base_url
        try:
            raw = await litellm.aembedding(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise map_litellm_error(exc) from exc
        return [Embedding(vector=list(item.get("embedding", []))) for item in raw.get("data", [])]

    # ---- 协议映射 / 请求构建 ----

    def _build_kwargs(self, request: LLMRequest, model: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.tools is not None:
            kwargs["tools"] = request.tools
        if self._api_key is not None:
            kwargs["api_key"] = self._api_key
        if self._base_url is not None:
            kwargs["api_base"] = self._base_url
        return kwargs

    def _map_response(self, raw: Any, model: str) -> LLMResponse:
        choice = cast(dict[str, Any], raw["choices"][0])
        message = cast(dict[str, Any], choice.get("message")) or {}
        usage = cast(dict[str, Any], raw.get("usage")) or {}
        return LLMResponse(
            content=str(message.get("content") or ""),
            usage=TokenUsage(
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
            ),
            finish_reason=str(choice.get("finish_reason") or "stop"),
            provider="litellm",
            model=model,
        )

    def _map_chunk(self, part: Any) -> LLMChunk:
        choices = cast(list[Any], part.get("choices", []))
        if not choices:
            return LLMChunk(content="")
        delta = cast(dict[str, Any], choices[0].get("delta")) or {}
        return LLMChunk(content=str(delta.get("content") or ""))

    def _backoff(self, attempt: int) -> float:
        return min(2 ** (attempt - 1) * 0.5, 8.0)  # 0.5s 起，指数退避，8s 封顶
