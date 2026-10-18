"""检索批量语义相似（change 0290 / ADR-0280 / 台账 E226）。

此前 `MemoryStore.read` 逐候选调用 embedder：N 条候选 ⇒ N 次远端调用；且在运行中
事件循环内该调用因嵌套 ``asyncio.run`` 失败，粘性降级后整个进程只剩词法检索。
现改为排序前按批向量化（query 至多一次），任一批失败 ⇒ 本次检索**整体**走 BM25。
"""

from __future__ import annotations

import asyncio

from core.llm_provider import (
    Embedding,
    LLMChunk,
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
)
from core.memory import MemoryEntry, MemoryStore
from core.memory.relevance import batch_similarities
from core.rag import LLMEmbedder


def _entry(entry_id: str, content: str) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=[],
        source="loop",
        trace_id="t",
        ts=1000.0,
        kind="episodic",
    )


# ---- batch_similarities 契约 ----


def test_batch_similarities_returns_cosine_map() -> None:
    """逐条余弦进入映射；``0.0`` 与负值是合法相似度（必须保留）。"""
    entries = [_entry("a", "x"), _entry("b", "y"), _entry("c", "z")]
    vectors = {"q": [1.0, 0.0], "x": [1.0, 0.0], "y": [0.0, 1.0], "z": [-1.0, 0.0]}

    def embedder(texts: list[str]) -> list[list[float]]:
        return [vectors[text] for text in texts]

    assert batch_similarities(entries, "q", embedder) == {
        "a": 1.0,
        "b": 0.0,
        "c": -1.0,
    }


def test_batch_similarities_chunks_and_embeds_query_once() -> None:
    """按批切分；query 只出现在第一批，全文只向量化一次。"""
    entries = [_entry(f"e{i}", f"c{i}") for i in range(5)]
    calls: list[list[str]] = []

    def embedder(texts: list[str]) -> list[list[float]]:
        calls.append(list(texts))
        return [[1.0, 0.0] for _ in texts]

    sims = batch_similarities(entries, "q", embedder, batch_size=2)

    assert calls == [["q", "c0"], ["c1", "c2"], ["c3", "c4"]]
    assert set(sims or {}) == {f"e{i}" for i in range(5)}


def test_batch_similarities_default_batch_size_is_bounded() -> None:
    """默认批 64：130 条文本 ⇒ 64/64/2 三次调用。"""
    entries = [_entry(f"e{i}", f"c{i}") for i in range(129)]
    calls: list[list[str]] = []

    def embedder(texts: list[str]) -> list[list[float]]:
        calls.append(list(texts))
        return [[1.0] for _ in texts]

    assert batch_similarities(entries, "q", embedder) is not None
    assert [len(call) for call in calls] == [64, 64, 2]
    flattened = [text for call in calls for text in call]
    assert len(flattened) == 130  # noqa: PLR2004 — 129 条内容 + 1 次 query
    assert flattened.count("q") == 1


def test_batch_similarities_empty_entries_returns_empty_without_embedding() -> None:
    """空候选集不调用 embedder（避免空读的瞬时失败毒化粘性降级）。"""

    def embedder(texts: list[str]) -> list[list[float]]:
        raise AssertionError("empty candidate set must not call embedder")  # noqa: TRY003

    assert batch_similarities([], "q", embedder) == {}


def test_batch_similarities_returns_none_on_embedder_error() -> None:
    def embedder(texts: list[str]) -> list[list[float]]:
        raise LLMError("embedding down")  # noqa: TRY003

    assert batch_similarities([_entry("a", "x")], "q", embedder) is None


def test_batch_similarities_returns_none_on_vector_count_mismatch() -> None:
    """返回向量数与输入文本数不符 ⇒ 整次降级（不接受部分映射）。"""

    def embedder(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0]]

    assert batch_similarities([_entry("a", "x"), _entry("b", "y")], "q", embedder) is None


def test_batch_similarities_returns_none_on_dimension_mismatch() -> None:
    """维度不一致 ⇒ ``None``（``_cosine`` 的 zip 会静默截断，先行拒绝）。"""

    def embedder(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0]] + [[1.0, 0.0, 0.0] for _ in texts[1:]]

    assert batch_similarities([_entry("a", "x")], "q", embedder) is None


# ---- 事件循环内端到端 ----


class _VectorProvider(LLMProvider):
    """按文本查表的假 provider：模拟「语义相关但词面不重叠」的向量。"""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        raise AssertionError("not used")  # noqa: TRY003

    async def astream(self, request: LLMRequest):
        yield LLMChunk(content="")

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        return [Embedding(vector=self._vectors[text]) for text in texts]


def test_memory_read_semantic_inside_running_loop() -> None:
    """原始缺陷的直接回归：循环内 read 仍按语义排序，不因嵌套 asyncio.run 降级词法。"""
    vectors = {
        "how to invalidate cache": [1.0, 0.0],  # query
        "stale entries must expire": [1.0, 0.0],  # gold：语义相关、词面零重叠
        "how to invalidate cache notes": [0.0, 1.0],  # 干扰：词面全覆盖、语义无关
    }
    store = MemoryStore(embedder=LLMEmbedder(_VectorProvider(vectors)).embed_many)
    store.write("L2", _entry("gold", "stale entries must expire"))
    store.write("L2", _entry("distractor", "how to invalidate cache notes"))

    async def main() -> list[str]:
        return [entry.id for entry in store.read("how to invalidate cache", budget=100)]

    assert asyncio.run(main())[0] == "gold"
