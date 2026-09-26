"""LLMProvider 抽象接口（llm-provider）。

异步为主（acompletion / astream / aembedding），同步为薄壳（completion /
stream / embedding），内部经事件循环桥接（asyncio.run）完成调用，语义与
异步入口一致。内核 loop 只依赖此接口，替换实现零改动。

对应接口：doc/03-interfaces/llm-provider-interface.md §1
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator

from .models import Embedding, LLMChunk, LLMRequest, LLMResponse


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

    # ---- 同步薄壳：内部 asyncio.run 桥接，语义与异步入口一致 ----

    def completion(self, request: LLMRequest) -> LLMResponse:
        return asyncio.run(self.acompletion(request))

    def stream(self, request: LLMRequest) -> Iterator[LLMChunk]:
        yield from asyncio.run(self._collect_stream(request))

    def embedding(self, texts: list[str]) -> list[Embedding]:
        return asyncio.run(self.aembedding(texts))

    async def _collect_stream(self, request: LLMRequest) -> list[LLMChunk]:
        return [chunk async for chunk in self.astream(request)]
