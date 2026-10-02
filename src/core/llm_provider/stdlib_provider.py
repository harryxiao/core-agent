"""OpenAI 兼容 stdlib 默认实现与错误归一化（llm-provider）。

默认实现：stdlib ``urllib.request`` 直连 OpenAI 兼容端点（单一 endpoint 即路由），
零第三方运行时依赖；底层 HTTP 异常统一经 ``map_http_error`` 归一到 ``LLMError``
层级；调用路径内置指数退避重试、超时控制与降级切换备用模型。

对应接口：doc/03-interfaces/llm-provider-interface.md §3 / §5
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any, cast

from .errors import (
    LLMAuthError,
    LLMError,
    LLMNetworkError,
    LLMRateLimitedError,
    LLMTimeoutError,
    UnknownProviderError,
)
from .models import Embedding, LLMChunk, LLMRequest, LLMResponse, TokenUsage, ToolCall
from .provider import LLMProvider

# 可重试错误：限流 / 网络抖动 / 超时（鉴权等非瞬时错误不重试）
_RETRYABLE = (LLMRateLimitedError, LLMNetworkError, LLMTimeoutError)

# HTTP 状态码 → 领域异常（未命中兜底 LLMError）
_HTTP_STATUS_ERRORS: dict[int, type[LLMError]] = {
    401: LLMAuthError,
    403: LLMAuthError,
    408: LLMTimeoutError,
    429: LLMRateLimitedError,
    504: LLMTimeoutError,
}

# SSE 流结束哨兵（跨线程入队）
_END: Any = object()


def map_http_error(exc: Exception) -> LLMError:
    """把 urllib / HTTP 传输异常归一为领域异常（不泄漏原始异常结构）。

    顺序关键：``HTTPError``（状态码语义）→ ``TimeoutError``（超时）→
    ``URLError``（网络不可达）→ 兜底 ``LLMError``。
    """
    if isinstance(exc, urllib.error.HTTPError):
        return _HTTP_STATUS_ERRORS.get(exc.code, LLMError)(str(exc))
    if isinstance(exc, TimeoutError):
        return LLMTimeoutError(str(exc))
    if isinstance(exc, urllib.error.URLError):
        return LLMNetworkError(str(exc))
    return LLMError(str(exc))


def _iter_sse_payloads(resp: Any) -> Iterator[str]:
    """逐行解析 SSE ``data:`` 帧，产出 JSON payload 字符串，遇 ``[DONE]`` 终止。"""
    for raw_line in resp:
        line = raw_line.decode("utf-8").strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if payload == "[DONE]":
            break
        yield payload


class StdlibLLMProvider(LLMProvider):
    """默认实现：stdlib 直连 OpenAI 兼容端点（零第三方运行时依赖）。"""

    def __init__(  # noqa: PLR0913, PLR0917 — 可选配置参数多，构造注入
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
                    self._call_provider(request, model), timeout=self._timeout
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

    async def _call_provider(self, request: LLMRequest, model: str) -> LLMResponse:
        body = self._build_body(request, model, stream=False)
        try:
            raw = await asyncio.to_thread(self._post_json, body)
        except Exception as exc:  # noqa: BLE001 — 底层 HTTP 异常统一归一
            raise map_http_error(exc) from exc
        return self._map_response(raw, model)

    async def astream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Any] = asyncio.Queue()

        def _put(item: Any) -> None:
            # asyncio.Queue 非线程安全，跨线程入队须经 call_soon_threadsafe
            loop.call_soon_threadsafe(queue.put_nowait, item)

        def _produce() -> None:
            try:
                body = self._build_body(request, request.model, stream=True)
                req = self._make_request(body, "chat/completions")
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    for payload in _iter_sse_payloads(resp):
                        _put(self._map_chunk(json.loads(payload)))
            except Exception as exc:  # noqa: BLE001 — 断流 / 底层异常统一归一
                _put(map_http_error(exc))
            finally:
                _put(_END)

        loop.run_in_executor(None, _produce)
        while True:
            item = await queue.get()
            if item is _END:
                return
            if isinstance(item, LLMError):
                raise item
            yield item

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        if self._model is None:
            raise UnknownProviderError("embedding 需在构造时指定 model")  # noqa: TRY003
        body: dict[str, Any] = {"model": self._model, "input": texts}
        try:
            raw = await asyncio.to_thread(self._post_embedding, body)
        except Exception as exc:  # noqa: BLE001
            raise map_http_error(exc) from exc
        return [Embedding(vector=list(item.get("embedding", []))) for item in raw.get("data", [])]

    # ---- 协议映射 / 请求构建 ----

    def _build_body(self, request: LLMRequest, model: str, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.tools is not None:
            body["tools"] = request.tools
        if request.reasoning_effort is not None:
            body["reasoning_effort"] = request.reasoning_effort
        if stream:
            body["stream"] = True
        return body

    def _make_request(self, body: dict[str, Any], path: str) -> urllib.request.Request:
        if self._base_url is None:
            raise UnknownProviderError("base_url 未配置，无法直连 OpenAI 兼容端点")  # noqa: TRY003
        headers = {"Content-Type": "application/json"}
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return urllib.request.Request(
            f"{self._base_url.rstrip('/')}/{path}",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

    def _post_json(self, body: dict[str, Any]) -> dict[str, Any]:
        req = self._make_request(body, "chat/completions")
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return cast(dict[str, Any], json.loads(resp.read().decode("utf-8")))

    def _post_embedding(self, body: dict[str, Any]) -> dict[str, Any]:
        req = self._make_request(body, "embeddings")
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return cast(dict[str, Any], json.loads(resp.read().decode("utf-8")))

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
            provider="stdlib",
            model=model,
            tool_calls=self._map_tool_calls(message.get("tool_calls")),
        )

    def _map_chunk(self, part: Any) -> LLMChunk:
        choices = cast(list[Any], part.get("choices", []))
        if not choices:
            return LLMChunk(content="")
        delta = cast(dict[str, Any], choices[0].get("delta")) or {}
        return LLMChunk(
            content=str(delta.get("content") or ""),
            tool_calls=self._map_tool_calls(delta.get("tool_calls")),
        )

    @staticmethod
    def _map_tool_calls(raw: Any) -> list[ToolCall] | None:
        """OpenAI 兼容 tool_calls 数组 → 统一 ToolCall。

        流式片段原样透传（``index`` 分组、``arguments`` 为增量段），完整响应则为
        拼好的参数 JSON 字符串；累积/解析由上层消费方收口。
        """
        if not raw:
            return None
        calls: list[ToolCall] = []
        for item in cast(list[Any], raw):
            entry = cast(dict[str, Any], item)
            function = cast(dict[str, Any], entry.get("function")) or {}
            calls.append(
                ToolCall(
                    tool_id=str(function.get("name") or ""),
                    arguments=str(function.get("arguments") or ""),
                    call_id=str(entry["id"]) if entry.get("id") else None,
                    index=int(entry.get("index", 0) or 0),
                )
            )
        return calls

    def _backoff(self, attempt: int) -> float:
        return min(2 ** (attempt - 1) * 0.5, 8.0)  # 0.5s 起，指数退避，8s 封顶
