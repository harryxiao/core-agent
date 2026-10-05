"""检索增强生成主链路门面（rag）。

把摄取（``IngestionPipeline``）· 检索（``Retriever``）· 生成融合（``RagGenerator``）
收口于**一处装配**：CLI / 宿主只需构造一次 ``RagService``，无需各自拼装四个对象
（装配知识不渗进调用方，也不产生第二真源）。生成器缺省不装配 —— 此时 ``ask``
以 ``GENERATION_UNAVAILABLE`` 结构化拒绝（fail-closed），``ingest`` / ``search``
不受影响。

对应接口：doc/03-interfaces/rag-interface.md §1 / §5 / §7
"""

from __future__ import annotations

import hashlib

from .embedder import Embedder
from .errors import RAGError, RAGErrorCode
from .generator import RagGenerator
from .ingest import IngestionPipeline
from .models import Document, SearchHit
from .retriever import Retriever
from .vector_store import VectorStore


def _content_hash(text: str) -> str:
    """文档内容指纹（sha256 前 16 位）：增量重建的变更判据，跨进程确定。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class RagService:
    """检索增强链路门面：摄取 / 检索 / 生成三段共用同一 embedding 与落盘索引。"""

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        *,
        chunk_size: int = 512,
        generator: RagGenerator | None = None,
        top_k: int = 5,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._pipeline = IngestionPipeline(embedder, store, chunk_size=chunk_size)
        self._retriever = Retriever(embedder, store)
        self._generator = generator
        self._top_k = top_k

    @property
    def embedder_name(self) -> str:
        """当前 embedding 后端名（``HashEmbedder`` = 离线降级基线，供调用方提示质量受限）。"""
        return type(self._embedder).__name__

    def ingest(self, doc_id: str, content: str) -> int:
        """摄取 / 刷新一份知识文档；返回本次写入块数（内容未变 ⇒ 0，不重复重建）。"""
        doc = Document(doc_id=doc_id, content=content, content_hash=_content_hash(content))
        return self._pipeline.ingest(doc)

    def refresh(self, doc_id: str, content: str) -> bool:
        """按 content_hash 检测变更并增量重建；返回是否触发重建。"""
        return self.ingest(doc_id, content) > 0

    def search(self, query: str, *, top_k: int | None = None) -> list[SearchHit]:
        """语义检索：query → embedding → 向量库 top-k 片段（相似度降序）。"""
        return self._retriever.search(query, top_k=top_k if top_k is not None else self._top_k)

    def ask(self, query: str, *, top_k: int | None = None) -> str:
        """检索增强生成：片段经预算裁剪注入生成链路；生成器未装配时结构化拒绝。"""
        if self._generator is None:
            raise RAGError(
                RAGErrorCode.GENERATION_UNAVAILABLE,
                "检索增强生成未装配生成器（需 llm-provider 通路），不返回空答案",
            )
        return self._generator.generate(query, self.search(query, top_k=top_k))
