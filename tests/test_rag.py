"""rag 单元测试（对齐 §13 契约 + M3 验收锚点）。

覆盖：embedding 确定性归一化 / 向量库增删查检索排序 / 文档摄取分块与增量重建 /
检索 top-k / 生成融合上下文注入与纯 LLM 降级 / LLM 错误归一化为 RAG 错误码。
"""

from __future__ import annotations

import math

import pytest

from core.llm_provider import (
    Embedding,
    LLMChunk,
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
from core.rag import (
    Chunk,
    Document,
    Embedder,
    HashEmbedder,
    IngestionPipeline,
    InMemoryVectorStore,
    LLMEmbedder,
    RAGError,
    RAGErrorCode,
    RagGenerator,
    Retriever,
    SearchHit,
)


def _resp(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
        finish_reason="stop",
        provider="stub",
        model="stub",
    )


class _StubProvider(LLMProvider):
    """记录请求的桩 provider：acompletion 返回固定 content，aembedding 返回固定向量。"""

    def __init__(self, reply: str = "answer") -> None:
        self._reply = reply
        self.last_request: LLMRequest | None = None

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        self.last_request = request
        return _resp(self._reply)

    async def astream(self, request: LLMRequest):
        yield LLMChunk(content=self._reply)

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        return [Embedding(vector=[1.0, 0.0]) for _ in texts]


class _FailingEmbeddingProvider(_StubProvider):
    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        raise LLMError("embedding down")  # noqa: TRY003


class _FixedEmbedder(Embedder):
    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0]


# ---- embedding ----


def test_hash_embedder_deterministic_and_normalized() -> None:
    dim = 16
    e = HashEmbedder(dim=dim)
    v1 = e.embed("hello world")
    v2 = e.embed("hello world")
    assert v1 == v2
    assert len(v1) == dim
    norm = math.sqrt(sum(x * x for x in v1))
    assert norm == pytest.approx(1.0, rel=1e-6)


def test_hash_embedder_empty_text_zero_vector() -> None:
    e = HashEmbedder(dim=8)
    assert e.embed("") == [0.0] * 8


def test_llm_embedder_maps_llm_error() -> None:
    embedder = LLMEmbedder(_FailingEmbeddingProvider())
    with pytest.raises(RAGError) as exc:
        embedder.embed("text")
    assert exc.value.code == RAGErrorCode.EMBEDDING_FAILED


# ---- 向量存储 ----


def test_in_memory_store_put_get_delete() -> None:
    store = InMemoryVectorStore()
    store.put(Chunk("c1", "d1", "x", [1.0]))
    assert store.get("c1") is not None
    assert store.get("missing") is None
    store.put(Chunk("c2", "d2", "y", [1.0]))
    store.delete("d1")
    assert store.get("c1") is None
    assert store.get("c2") is not None


def test_in_memory_store_search_ranks_by_similarity() -> None:
    store = InMemoryVectorStore()
    store.put(Chunk("c1", "d1", "a", [1.0, 0.0]))
    store.put(Chunk("c2", "d1", "b", [0.0, 1.0]))
    store.put(Chunk("c3", "d2", "c", [0.5, 0.5]))
    hits = store.search([1.0, 0.0], top_k=2)
    assert [h.chunk.chunk_id for h in hits] == ["c1", "c3"]


# ---- 摄取管线 ----


def test_ingest_chunks_long_document() -> None:
    e = HashEmbedder(dim=16)
    store = InMemoryVectorStore()
    pipeline = IngestionPipeline(e, store, chunk_size=10)
    pipeline.ingest(Document("d1", "0123456789abcdefghij", "h1"))
    assert store.get("d1#0") is not None
    assert store.get("d1#1") is not None
    assert store.get("d1#2") is None


def test_refresh_no_change_returns_false() -> None:
    pipeline = IngestionPipeline(HashEmbedder(dim=16), InMemoryVectorStore())
    doc = Document("d1", "hello", "h1")
    pipeline.ingest(doc)
    assert pipeline.refresh(doc) is False


def test_refresh_change_rebuilds() -> None:
    store = InMemoryVectorStore()
    pipeline = IngestionPipeline(HashEmbedder(dim=16), store)
    pipeline.ingest(Document("d1", "old", "h1"))
    assert pipeline.refresh(Document("d1", "new content", "h2")) is True
    chunk = store.get("d1#0")
    assert chunk is not None
    assert chunk.text == "new content"


# ---- 检索 ----


def test_retriever_delegates_to_store() -> None:
    store = InMemoryVectorStore()
    store.put(Chunk("c1", "d1", "match", [1.0, 0.0]))
    store.put(Chunk("c2", "d1", "no", [0.0, 1.0]))
    retriever = Retriever(_FixedEmbedder(), store)
    hits = retriever.search("query", top_k=1)
    assert len(hits) == 1
    assert hits[0].chunk.chunk_id == "c1"


# ---- 生成融合 ----


def test_rag_generator_injects_context() -> None:
    provider = _StubProvider("answer")
    gen = RagGenerator(provider)
    hits = [SearchHit(chunk=Chunk("c1", "d1", "片段内容", [1.0]), score=0.9)]
    reply = gen.generate("问题", hits)
    assert reply == "answer"
    assert provider.last_request is not None
    prompt = provider.last_request.messages[0].content
    assert "片段内容" in prompt
    assert "问题" in prompt


def test_rag_generator_empty_hits_pure_llm() -> None:
    provider = _StubProvider("answer")
    gen = RagGenerator(provider)
    assert gen.generate("问题", []) == "answer"
    assert provider.last_request is not None
    assert provider.last_request.messages[0].content == "问题"
