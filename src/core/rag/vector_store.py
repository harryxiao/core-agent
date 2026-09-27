"""向量存储抽象与实现（rag）。

``VectorStore`` 抽象隔离底层向量库：生产默认 sqlite-vec 嵌入式落盘（零服务），
经本抽象替换实现时调用方零改动；离线缺省 ``InMemoryVectorStore`` 以纯内存 +
余弦相似度满足「零服务、零外部依赖」可运行基线（M3）。

对应接口：doc/03-interfaces/rag-interface.md §1 / §6
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod

from .models import Chunk, SearchHit


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """两个向量余弦相似度；任一方为空或零向量返回 0.0。"""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorStore(ABC):
    """向量存储抽象接口：写入 / 读取 / 按文档删除 / top-k 相似度检索。"""

    @abstractmethod
    def put(self, chunk: Chunk) -> None:
        """写入块向量并建索引。"""
        raise NotImplementedError

    @abstractmethod
    def get(self, chunk_id: str) -> Chunk | None:
        """按块 id 读取；不存在返回 None。"""
        raise NotImplementedError

    @abstractmethod
    def delete(self, doc_id: str) -> None:
        """删除某文档的全部块（增量重建前清旧块）。"""
        raise NotImplementedError

    @abstractmethod
    def search(self, embedding: list[float], *, top_k: int = 5) -> list[SearchHit]:
        """按向量相似度返回 top-k 命中（得分降序）。"""
        raise NotImplementedError


class InMemoryVectorStore(VectorStore):
    """纯内存向量存储：dict 索引 + 余弦相似度，零第三方依赖。"""

    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}

    def put(self, chunk: Chunk) -> None:
        self._chunks[chunk.chunk_id] = chunk

    def get(self, chunk_id: str) -> Chunk | None:
        return self._chunks.get(chunk_id)

    def delete(self, doc_id: str) -> None:
        for chunk_id in [cid for cid, c in self._chunks.items() if c.doc_id == doc_id]:
            del self._chunks[chunk_id]

    def search(self, embedding: list[float], *, top_k: int = 5) -> list[SearchHit]:
        scored = [
            SearchHit(chunk=c, score=_cosine_similarity(embedding, c.embedding))
            for c in self._chunks.values()
            if c.embedding
        ]
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:top_k]
