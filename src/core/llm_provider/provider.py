"""LLMProvider 抽象接口（llm-provider）。

异步为主（acompletion / astream / aembedding），同步为薄壳（completion /
stream / embedding）：无运行事件循环时直接 ``asyncio.run``；已有运行循环时
在一次性工作线程的新循环中执行同一异步实现并等待结果（change 0290 /
ADR-0280）。同步薄壳在两种上下文中都**阻塞**，非阻塞调用方用异步入口。
内核 loop 只依赖此接口，替换实现零改动。

对应接口：doc/03-interfaces/llm-provider-interface.md §1
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from .models import Embedding, LLMChunk, LLMRequest, LLMResponse

_T = TypeVar("_T")


def _run_sync(factory: Callable[[], Coroutine[Any, Any, _T]]) -> _T:
    """把异步实现桥接为同步调用（循环安全）。

    传入**协程工厂**而非协程：桥接本身失败时不会留下未等待协程。运行中事件循环内
    同步等待会死锁，故改在一次性工作线程中 ``asyncio.run``；不用进程级单 worker
    （worker 内再调同步薄壳会互相等待）。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(factory())).result()


class LLMProvider(ABC):
    """三方大模型归一化抽象接口。"""

    @abstractmethod
    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        """异步补全。"""
        raise NotImplementedError

    @abstractmethod
    def astream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        """异步流式补全：返回可 ``async for`` 迭代的异步迭代器（异步生成器）。"""
        raise NotImplementedError

    @abstractmethod
    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        """异步向量化。"""
        raise NotImplementedError

    # ---- 同步薄壳：循环安全桥接，语义与异步入口一致（两种上下文均阻塞）----

    def completion(self, request: LLMRequest) -> LLMResponse:
        return _run_sync(lambda: self.acompletion(request))

    def stream(self, request: LLMRequest) -> Iterator[LLMChunk]:
        yield from _run_sync(lambda: self._collect_stream(request))

    def embedding(self, texts: list[str]) -> list[Embedding]:
        return _run_sync(lambda: self.aembedding(texts))

    async def _collect_stream(self, request: LLMRequest) -> list[LLMChunk]:
        return [chunk async for chunk in self.astream(request)]
