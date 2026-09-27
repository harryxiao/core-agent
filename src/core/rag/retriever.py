"""语义检索（rag）。

查询语句 → embedding → VectorStore.search，返回按相似度降序的 top-k 片段及
相关度得分。

对应接口：doc/03-interfaces/rag-interface.md §4
"""

from __future__ import annotations

from .embedder import Embedder
from .models import SearchHit
from .vector_store import VectorStore


class Retriever:
    """语义检索器：query embedding → 向量库 top-k 检索。"""

    def __init__(self, embedder: Embedder, store: VectorStore) -> None:
        self._embedder = embedder
        self._store = store

    def search(self, query: str, *, top_k: int = 5) -> list[SearchHit]:
        """查询语句 embedding → VectorStore.search，返回 top-k 片段 + 相关度得分。"""
        embedding = self._embedder.embed(query)
        return self._store.search(embedding, top_k=top_k)
