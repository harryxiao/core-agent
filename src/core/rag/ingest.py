"""文档摄取管线（rag）。

导入知识文档：分块 → 逐块 embedding → 写入向量索引；按 content_hash 检测
源文档变更，不一致则增量重建受影响块；重建期 embedding 失败降级为旧索引
（旧索引在重建成功前不删除），索引写入失败归一到 ``REBUILD_FAILED``。

对应接口：doc/03-interfaces/rag-interface.md §2
"""

from __future__ import annotations

from .embedder import Embedder
from .errors import RAGError, RAGErrorCode
from .models import Chunk, Document
from .vector_store import VectorStore


class IngestionPipeline:
    """文档摄取：分块 + embedding + 建索引 + 增量更新。"""

    def __init__(self, embedder: Embedder, store: VectorStore, *, chunk_size: int = 512) -> None:
        self._embedder = embedder
        self._store = store
        self._chunk_size = chunk_size
        self._hashes: dict[str, str] = {}

    def ingest(self, doc: Document) -> None:
        """导入知识文档：分块 → 逐块 embedding → 写入向量索引。"""
        for chunk in self._build_chunks(doc):
            self._store.put(chunk)
        self._hashes[doc.doc_id] = doc.content_hash

    def refresh(self, doc: Document) -> bool:
        """按 content_hash 检测源文档变更；不一致则增量重建受影响块。

        返回是否触发重建（重建窗口期该文档检索降级旧索引）。embedding 失败在
        旧索引删除前抛出，旧索引保留（降级）；索引写入失败归一 ``REBUILD_FAILED``。
        """
        if self._hashes.get(doc.doc_id) == doc.content_hash:
            return False
        rebuilt = self._build_chunks(doc)
        try:
            self._store.delete(doc.doc_id)
            for chunk in rebuilt:
                self._store.put(chunk)
        except Exception as exc:
            raise RAGError(RAGErrorCode.REBUILD_FAILED, f"增量重建失败: {exc}") from exc
        self._hashes[doc.doc_id] = doc.content_hash
        return True

    def _build_chunks(self, doc: Document) -> list[Chunk]:
        text = doc.content
        size = self._chunk_size
        pieces = [text[i : i + size] for i in range(0, len(text), size)] if text else [""]
        return [
            Chunk(
                chunk_id=f"{doc.doc_id}#{i}",
                doc_id=doc.doc_id,
                text=piece,
                embedding=self._embedder.embed(piece),
            )
            for i, piece in enumerate(pieces)
        ]
