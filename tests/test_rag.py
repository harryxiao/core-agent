"""rag 单元测试（对齐 §13 契约 + M3 验收锚点）。

覆盖：embedding 确定性归一化 / 向量库增删查检索排序 / 文档摄取分块与增量重建 /
检索 top-k / 生成融合上下文注入与纯 LLM 降级 / LLM 错误归一化为 RAG 错误码。
"""

from __future__ import annotations

import asyncio
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
    RagService,
    Retriever,
    SearchHit,
    SqliteVectorStore,
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


class _RecordingEmbeddingProvider(_StubProvider):
    """记录每次 embedding 调用的文本批（change 0290 / ADR-0280）。"""

    def __init__(self) -> None:
        super().__init__()
        self.batches: list[list[str]] = []

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        self.batches.append(list(texts))
        return [Embedding(vector=[float(len(t)), 1.0]) for t in texts]


def test_llm_embedder_embed_many_calls_provider_once() -> None:
    """批量入口一次 provider 调用收齐全部文本（不是逐条）。"""
    provider = _RecordingEmbeddingProvider()
    vectors = LLMEmbedder(provider).embed_many(["a", "bbb", "cc"])

    assert vectors == [[1.0, 1.0], [3.0, 1.0], [2.0, 1.0]]
    assert provider.batches == [["a", "bbb", "cc"]]


def test_llm_embedder_embed_many_maps_llm_error() -> None:
    embedder = LLMEmbedder(_FailingEmbeddingProvider())
    with pytest.raises(RAGError) as exc:
        embedder.embed_many(["text"])
    assert exc.value.code == RAGErrorCode.EMBEDDING_FAILED
    assert isinstance(exc.value.__cause__, LLMError)


def test_llm_embedder_embed_many_empty_returns_empty() -> None:
    """空输入不触网（provider 永不被调用）。"""

    class _NeverCalled(_StubProvider):
        async def aembedding(self, texts: list[str]) -> list[Embedding]:
            raise AssertionError("empty batch must not reach provider")  # noqa: TRY003

    assert LLMEmbedder(_NeverCalled()).embed_many([]) == []


def test_llm_embedder_embed_many_inside_running_loop() -> None:
    """运行中事件循环内仍可批量向量化（同步薄壳桥接，change 0290）。"""
    embedder = LLMEmbedder(_RecordingEmbeddingProvider())

    async def main() -> list[list[float]]:
        return embedder.embed_many(["a", "bb"])

    assert asyncio.run(main()) == [[1.0, 1.0], [2.0, 1.0]]


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


# ---- 落盘向量库（change 0104） ----


def test_sqlite_store_put_get_delete(tmp_path) -> None:
    store = SqliteVectorStore(tmp_path / "rag-index.db")
    store.put(Chunk("c1", "d1", "x", [1.0, 0.0]))
    store.put(Chunk("c2", "d2", "y", [0.0, 1.0]))

    assert store.get("c1") is not None
    assert store.get("c1").text == "x"  # type: ignore[union-attr]
    assert store.get("missing") is None

    store.delete("d1")

    assert store.get("c1") is None, "按文档删除清掉该文档全部块"
    assert store.get("c2") is not None


def test_sqlite_store_search_ranks_by_similarity(tmp_path) -> None:
    store = SqliteVectorStore(tmp_path / "rag-index.db")
    store.put(Chunk("c1", "d1", "a", [1.0, 0.0]))
    store.put(Chunk("c2", "d1", "b", [0.0, 1.0]))
    store.put(Chunk("c3", "d2", "c", [0.5, 0.5]))

    hits = store.search([1.0, 0.0], top_k=2)

    assert [h.chunk.chunk_id for h in hits] == ["c1", "c3"]


def test_sqlite_store_reused_across_instances(tmp_path) -> None:
    """跨进程复用：新实例装载同一索引文件仍能命中（落盘为检索真源）。"""
    path = tmp_path / "rag-index.db"
    first = SqliteVectorStore(path)
    first.put(Chunk("c1", "d1", "部署流程", [1.0, 0.0]))

    second = SqliteVectorStore(path)
    hits = second.search([1.0, 0.0], top_k=1)

    assert [h.chunk.chunk_id for h in hits] == ["c1"], "块从落盘索引装载"
    assert hits[0].chunk.embedding == [1.0, 0.0], "向量往返无损"


def test_sqlite_store_rejects_dim_mismatch(tmp_path) -> None:
    """维度不一致 ⇒ 结构化拒绝（不静默按短边截断比较）。"""
    path = tmp_path / "rag-index.db"
    store = SqliteVectorStore(path)
    store.put(Chunk("c1", "d1", "x", [1.0, 0.0]))

    with pytest.raises(RAGError) as put_exc:
        store.put(Chunk("c2", "d2", "y", [1.0, 0.0, 0.0]))
    assert put_exc.value.code == RAGErrorCode.INDEX_CORRUPT

    reopened = SqliteVectorStore(path)
    with pytest.raises(RAGError) as search_exc:
        reopened.search([1.0, 0.0, 0.0])
    assert search_exc.value.code == RAGErrorCode.INDEX_CORRUPT


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


# ---- 主链路门面（change 0104） ----


def _service(tmp_path, *, provider: _StubProvider | None = None) -> RagService:
    store = SqliteVectorStore(tmp_path / "rag-index.db")
    generator = RagGenerator(provider) if provider is not None else None
    return RagService(_FixedEmbedder(), store, chunk_size=10, generator=generator)


def test_service_ingest_then_search(tmp_path) -> None:
    service = _service(tmp_path)

    chunks = service.ingest("d1", "0123456789abcdefghij")

    assert chunks == 2, "20 字符 / 块长 10 ⇒ 2 块"  # noqa: PLR2004
    hits = service.search("query", top_k=2)
    assert len(hits) == 2  # noqa: PLR2004
    assert hits[0].chunk.doc_id == "d1"
    assert service.search("query", top_k=1)[0].score > 0.0


def test_service_refresh_detects_change(tmp_path) -> None:
    service = _service(tmp_path)
    service.ingest("d1", "same content")

    assert service.refresh("d1", "same content") is False, "内容未变 ⇒ 不重建"
    assert service.refresh("d1", "changed content") is True, "内容变更 ⇒ 增量重建"


def test_service_ask_uses_retrieved_context(tmp_path) -> None:
    provider = _StubProvider("答案")
    service = _service(tmp_path, provider=provider)
    service.ingest("d1", "部署流程说明")

    assert service.ask("如何部署") == "答案"
    assert provider.last_request is not None
    assert "部署流程说明" in provider.last_request.messages[0].content, "命中片段注入生成提示词"


def test_service_ask_without_generator_is_structured_error(tmp_path) -> None:
    """未装配生成器（未配 LLM）⇒ 结构化错误提示，不静默给空答案。"""
    service = _service(tmp_path)
    service.ingest("d1", "内容")

    with pytest.raises(RAGError) as exc:
        service.ask("问题")

    assert exc.value.code == RAGErrorCode.GENERATION_UNAVAILABLE


def test_service_ask_empty_hits_degrades(tmp_path) -> None:
    """检索无命中 ⇒ 降级纯 LLM 生成（不阻断）。"""
    provider = _StubProvider("兜底答案")
    service = _service(tmp_path, provider=provider)

    assert service.ask("无索引的问题") == "兜底答案"
    assert provider.last_request is not None
    assert provider.last_request.messages[0].content == "无索引的问题"
