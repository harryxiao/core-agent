"""检索增强生成（rag，L3 检索底座）。

本地向量库（默认 sqlite-vec）+ 文档摄取分块 + 本地 embedding + 语义检索 +
生成融合；经 VectorStore / Embedder 抽象隔离，替换向量库或 embedding 后端
调用方零改动。

对应规格：doc/openspec/specs/rag/spec.md
"""

from .embedder import Embedder, HashEmbedder, LLMEmbedder
from .errors import RAGError, RAGErrorCode
from .generator import RagGenerator
from .ingest import IngestionPipeline
from .models import Chunk, Document, SearchHit
from .retriever import Retriever
from .vector_store import InMemoryVectorStore, VectorStore

__all__ = [
    "Chunk",
    "Document",
    "Embedder",
    "HashEmbedder",
    "InMemoryVectorStore",
    "IngestionPipeline",
    "LLMEmbedder",
    "RAGError",
    "RAGErrorCode",
    "RagGenerator",
    "Retriever",
    "SearchHit",
    "VectorStore",
]
