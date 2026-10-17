"""OpenAI 兼容 stdlib 默认实现与错误归一化（llm-provider）。

默认实现：stdlib ``urllib.request`` 直连 OpenAI 兼容端点（单一 endpoint 即路由），
零第三方运行时依赖；底层 HTTP 异常统一经 ``map_http_error`` 归一到 ``LLMError``
层级；调用路径内置指数退避重试、超时控制与降级切换备用模型。

传输走 ``HTTPConnectionPool``（同 origin 复用 keep-alive 连接）——见 ``http_pool`` 与 ADR-0064；
``transport`` 构造参数是该层的注入接缝（测试替身 / 换实现均不改本文件）。

对应接口：doc/03-interfaces/llm-provider-interface.md §3 / §5
"""

from __future__ import annotations

import asyncio
import contextlib
import http.client
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
from .http_pool import HTTPConnectionPool, HTTPTransport
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
    ``URLError``（网络不可达）→ ``http.client`` / 其余 ``OSError``（连接层）→ 兜底 ``LLMError``。
    后两类与 ``URLError`` 同口径（``LLMNetworkError``，可重试）：连接池直连 ``http.client``，
    其连接的拒绝 / 重置 / 状态行异常不带 urllib 包装，须在此归一到同一层级。
    """
    if isinstance(exc, urllib.error.HTTPError):
        return _HTTP_STATUS_ERRORS.get(exc.code, LLMError)(str(exc))
    if isinstance(exc, TimeoutError):
        return LLMTimeoutError(str(exc))
    if isinstance(exc, urllib.error.URLError):
        return LLMNetworkError(str(exc))
    if isinstance(exc, (OSError, http.client.HTTPException)):
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


def _thinking_text(message: dict[str, Any]) -> str:
    """推理原文归一（change `0145` / ADR-0137 / 账本 E56）。

    兼容**两家既有口径**：`reasoning_content`（GLM/DeepSeek 系）与 `reasoning`
    （OpenAI o 系）—— 前者优先。取值恒为字符串、**绝不掺入 `content`**（两字段分属
    正文与推理，拼接会污染回复正文与转录）；字段缺失 / 非字符串 ⇒ 空串（零回归）。
    """
    raw = message.get("reasoning_content") or message.get("reasoning")
    return raw if isinstance(raw, str) else ""


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
        transport: HTTPTransport | None = None,
        # 审计标签（change 0184 / ADR-0175）：组合根按 `llm.provider` 注入 ⇒ `LLMResponse.provider`
        # 反映**实际使用的 provider 标识**，不再是与配置无关的硬编码常量。空（未注入）⇒ 回落
        # 实现自身身份 `"stdlib"`（裸构造 / 测试替身的行为逐字不变）。
        provider: str = "stdlib",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._provider = provider or "stdlib"
        self._timeout = timeout
        self._max_retries = max_retries
        self._fallback = fallback_models if fallback_models is not None else []
        self._audit = audit
        self._transport: HTTPTransport = (
            transport if transport is not None else HTTPConnectionPool()
        )

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
        # 生产者线程持有的响应（超时时由消费端尽力关闭，避免读线程继续挂在长连接上）
        response: list[Any] = []

        def _put(item: Any) -> None:
            # asyncio.Queue 非线程安全，跨线程入队须经 call_soon_threadsafe
            loop.call_soon_threadsafe(queue.put_nowait, item)

        def _produce() -> None:
            try:
                body = self._build_body(request, request.model, stream=True)
                req = self._make_request(body, "chat/completions")
                with self._transport.send(req, timeout=self._timeout) as resp:
                    response.append(resp)
                    for payload in _iter_sse_payloads(resp):
                        _put(self._map_chunk(json.loads(payload)))
            except Exception as exc:  # noqa: BLE001 — 断流 / 底层异常统一归一
                _put(map_http_error(exc))
            finally:
                _put(_END)

        loop.run_in_executor(None, _produce)
        while True:
            item = await self._await_chunk(queue, response)
            if item is _END:
                return
            if isinstance(item, LLMError):
                raise item
            yield item

    async def _await_chunk(self, queue: asyncio.Queue[Any], response: list[Any]) -> Any:
        """等待下一个增量，**相邻增量间隔**超过 ``timeout`` ⇒ 释放响应并抛超时。

        socket 读超时管不到「连接活着但只发注释 / keep-alive」的端点——它们不入队
        ``data`` 帧，消费端会无限等待（change 0256）。已交付的增量不回滚，故不重试。
        """
        try:
            return await asyncio.wait_for(queue.get(), timeout=self._timeout)
        except TimeoutError as exc:
            for resp in response:
                with contextlib.suppress(Exception):
                    resp.close()
            raise LLMTimeoutError(  # noqa: TRY003 — 文案含动态上限，非可静态归类的异常类
                f"流式响应超时（>{self._timeout}s 无增量）"
            ) from exc

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
            # 要求端点在**末块**上报用量（change 0183 / ADR-0174）：非流式响应本就携带 `usage`，
            # 故该字段**只**下发给流式请求（不支持的端点会响亮报错，非静默降级）。
            body["stream_options"] = {"include_usage": True}
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
        return self._send_json(self._make_request(body, "chat/completions"))

    def _post_embedding(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._send_json(self._make_request(body, "embeddings"))

    def _send_json(self, req: urllib.request.Request) -> dict[str, Any]:
        with self._transport.send(req, timeout=self._timeout) as resp:
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
            provider=self._provider,
            model=model,
            tool_calls=self._map_tool_calls(message.get("tool_calls")),
            thinking=_thinking_text(message),
        )

    def _map_chunk(self, part: Any) -> LLMChunk:
        choices = cast(list[Any], part.get("choices", []))
        if not choices:
            # 用量末块在此形态（change 0183 / ADR-0174）：端点上报用量时，末块**只报账**、
            # `choices` 为空数组 ⇒ 必须在早返**之前**取用量，否则该数字永远丢失。
            return LLMChunk(content="", usage=self._map_usage(part))
        choice = cast(dict[str, Any], choices[0]) or {}
        delta = cast(dict[str, Any], choice.get("delta")) or {}
        return LLMChunk(
            content=str(delta.get("content") or ""),
            tool_calls=self._map_tool_calls(delta.get("tool_calls")),
            thinking=_thinking_text(delta),
            # 终止原因通常只在末块携带（缺省块为空串）⇒ 归因「被截断」的权威信号（change 0170）。
            finish_reason=str(choice.get("finish_reason") or ""),
            usage=self._map_usage(part),
        )

    @staticmethod
    def _map_usage(part: Any) -> TokenUsage | None:
        """流式增量顶层 `usage` → 统一 TokenUsage；未携带（缺键 / `null`）⇒ ``None``。

        **不**造零值：``None`` 意为「该块未报用量」（端点未开启上报），与「端点报零」
        在观测面必须可分辨（见 change 0183 / ADR-0174）。
        """
        usage = cast(dict[str, Any], part).get("usage")
        if not isinstance(usage, dict):
            return None
        fields = cast(dict[str, Any], usage)
        return TokenUsage(
            prompt_tokens=int(fields.get("prompt_tokens", 0)),
            completion_tokens=int(fields.get("completion_tokens", 0)),
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
