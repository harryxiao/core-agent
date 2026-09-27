"""RAG 数据模型（rag）。

块 / 检索命中 / 文档三类数据结构，供 VectorStore / IngestionPipeline /
Retriever / RagGenerator 消费。

对应接口：doc/03-interfaces/rag-interface.md §1 / §2
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    """文档分块：全局唯一块 id + 来源文档 + 文本 + 向量。"""

    chunk_id: str
    doc_id: str
    text: str
    embedding: list[float]


@dataclass
class SearchHit:
    """检索命中：块 + 向量相似度得分（供后续裁剪排序）。"""

    chunk: Chunk
    score: float


@dataclass
class Document:
    """待摄取知识文档：唯一 id + 原始文本 + 内容 hash（增量更新失效检测）。"""

    doc_id: str
    content: str
    content_hash: str
