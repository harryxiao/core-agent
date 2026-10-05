"""向量存储抽象与实现（rag）。

``VectorStore`` 抽象隔离底层向量库：默认实现 ``SqliteVectorStore`` 以 stdlib ``sqlite3``
嵌入式落盘（零服务、零三方依赖、跨进程复用），经本抽象替换为 ``sqlite-vec`` 等向量扩展时
调用方零改动；``InMemoryVectorStore`` 以纯内存 + 余弦相似度满足无落盘场景（测试 / 单次进程）。

对应接口：doc/03-interfaces/rag-interface.md §1 / §6
"""

from __future__ import annotations

import math
import sqlite3
from abc import ABC, abstractmethod
from array import array
from pathlib import Path

from .errors import RAGError, RAGErrorCode
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

    @abstractmethod
    def record_document(self, doc_id: str, content_hash: str) -> None:
        """记录文档内容指纹（增量重建的变更判据；落盘实现须跨进程可见）。"""
        raise NotImplementedError

    @abstractmethod
    def document_hash(self, doc_id: str) -> str | None:
        """读取文档内容指纹；未记录返回 None。"""
        raise NotImplementedError


class InMemoryVectorStore(VectorStore):
    """纯内存向量存储：dict 索引 + 余弦相似度，零第三方依赖。"""

    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}
        self._hashes: dict[str, str] = {}

    def put(self, chunk: Chunk) -> None:
        self._chunks[chunk.chunk_id] = chunk

    def get(self, chunk_id: str) -> Chunk | None:
        return self._chunks.get(chunk_id)

    def delete(self, doc_id: str) -> None:
        for chunk_id in [cid for cid, c in self._chunks.items() if c.doc_id == doc_id]:
            del self._chunks[chunk_id]
        self._hashes.pop(doc_id, None)

    def search(self, embedding: list[float], *, top_k: int = 5) -> list[SearchHit]:
        scored = [
            SearchHit(chunk=c, score=_cosine_similarity(embedding, c.embedding))
            for c in self._chunks.values()
            if c.embedding
        ]
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:top_k]

    def record_document(self, doc_id: str, content_hash: str) -> None:
        self._hashes[doc_id] = content_hash

    def document_hash(self, doc_id: str) -> str | None:
        return self._hashes.get(doc_id)


def _pack(vector: list[float]) -> bytes:
    """向量 → BLOB（float64 小端定长，跨进程无损往返）。"""
    return array("d", vector).tobytes()


def _unpack(blob: bytes) -> list[float]:
    """BLOB → 向量。"""
    values = array("d")
    values.frombytes(blob)
    return list(values)


class SqliteVectorStore(VectorStore):
    """stdlib ``sqlite3`` 落盘向量存储：嵌入式零服务、跨进程复用、零三方依赖。

    ``chunks`` 表存块（向量以 BLOB 落盘）、``documents`` 表存文档内容指纹（跨进程增量判定）、
    ``meta`` 表记索引**向量维度**（首个 ``put`` 定档；不一致即结构化拒绝，不静默截断比较）。
    相似度在进程内暴力余弦计算（规模未到 ANN 门槛）。
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS chunks ("
            "chunk_id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, text TEXT NOT NULL, "
            "embedding BLOB NOT NULL)"
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS chunks_doc_id ON chunks (doc_id)")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS documents ("
            "doc_id TEXT PRIMARY KEY, content_hash TEXT NOT NULL)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        self._conn.commit()

    def put(self, chunk: Chunk) -> None:
        self._check_dim(len(chunk.embedding), record=True)
        self._conn.execute(
            "INSERT INTO chunks (chunk_id, doc_id, text, embedding) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(chunk_id) DO UPDATE SET doc_id = excluded.doc_id, "
            "text = excluded.text, embedding = excluded.embedding",
            (chunk.chunk_id, chunk.doc_id, chunk.text, _pack(chunk.embedding)),
        )
        self._conn.commit()

    def get(self, chunk_id: str) -> Chunk | None:
        row = self._conn.execute(
            "SELECT chunk_id, doc_id, text, embedding FROM chunks WHERE chunk_id = ?",
            (chunk_id,),
        ).fetchone()
        return _row_to_chunk(row) if row is not None else None

    def delete(self, doc_id: str) -> None:
        self._conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        self._conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
        self._conn.commit()

    def search(self, embedding: list[float], *, top_k: int = 5) -> list[SearchHit]:
        self._check_dim(len(embedding), record=False)
        scored = [
            SearchHit(
                chunk=_row_to_chunk(row),
                score=_cosine_similarity(embedding, _unpack(row[3])),
            )
            for row in self._conn.execute(
                "SELECT chunk_id, doc_id, text, embedding FROM chunks"
            ).fetchall()
        ]
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:top_k]

    def record_document(self, doc_id: str, content_hash: str) -> None:
        self._conn.execute(
            "INSERT INTO documents (doc_id, content_hash) VALUES (?, ?) "
            "ON CONFLICT(doc_id) DO UPDATE SET content_hash = excluded.content_hash",
            (doc_id, content_hash),
        )
        self._conn.commit()

    def document_hash(self, doc_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT content_hash FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        return str(row[0]) if row is not None else None

    def _index_dim(self) -> int | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = 'dim'").fetchone()
        return int(row[0]) if row is not None else None

    def _check_dim(self, dim: int, *, record: bool) -> None:
        """维度一致性守护：首个写入定档；此后不符即以 ``INDEX_CORRUPT`` 结构化拒绝。"""
        known = self._index_dim()
        if known is None:
            if record and dim > 0:
                self._conn.execute(
                    "INSERT OR IGNORE INTO meta (key, value) VALUES ('dim', ?)", (str(dim),)
                )
                self._conn.commit()
            return
        if dim != known:
            raise RAGError(
                RAGErrorCode.INDEX_CORRUPT,
                f"索引向量维度 {known} ≠ 当前 embedding 维度 {dim}，须重建索引",
            )


def _row_to_chunk(row: tuple[str, str, str, bytes]) -> Chunk:
    return Chunk(chunk_id=row[0], doc_id=row[1], text=row[2], embedding=_unpack(row[3]))
