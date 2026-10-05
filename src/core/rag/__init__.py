"""检索增强生成（rag，L3 检索底座）。

落盘向量库（默认 stdlib `sqlite3`，零三方依赖）+ 文档摄取分块 + 本地 embedding +
语义检索 + 生成融合；经 VectorStore / Embedder 抽象隔离，替换向量库或 embedding
后端调用方零改动。主链路门面为 ``RagService``（摄取 / 检索 / 生成收口于一处装配）。

对应规格：doc/openspec/specs/rag/spec.md
"""

from .embedder import Embedder, HashEmbedder, LLMEmbedder
from .errors import RAGError, RAGErrorCode
from .generator import RagGenerator
from .ingest import IngestionPipeline
from .models import Chunk, Document, SearchHit
from .retriever import Retriever
from .service import RagService
from .vector_store import InMemoryVectorStore, SqliteVectorStore, VectorStore

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
    "RagService",
    "Retriever",
    "SearchHit",
    "SqliteVectorStore",
    "VectorStore",
]
