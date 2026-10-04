"""memory 单元测试（对齐规格场景 + M1 验收锚点）。

覆盖：分层写入落对层 + L1 最小索引、read 相关性排序 + 预算截断、
热/冷检索 + 失败降级、无行动不写入、结晶/溶解、并发写入不丢条目。
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from core.memory import (
    Crystallizer,
    FileBackend,
    Layer,
    MemoryEntry,
    MemoryStore,
)
from core.memory.embedding import batch_embed


def _entry(
    entry_id: str,
    layer: Layer,
    content: str,
    source: str = "loop",
    trace_id: str = "t",
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer=layer,
        content=content,
        tags=[],
        source=source,
        trace_id=trace_id,
    )


def test_write_lands_correct_layer_and_index() -> None:
    store = MemoryStore()
    store.write("L2", _entry("e1", "L2", "事实 A"))
    assert store.index().entries == [("e1", "L2")]  # L1 索引最小：仅 (id, layer)


def test_read_relevance_order() -> None:
    store = MemoryStore()
    store.write("L2", _entry("e1", "L2", "apple banana cherry"))
    store.write("L2", _entry("e2", "L2", "apple"))
    results = store.read("apple cherry", budget=100)
    assert [e.id for e in results] == ["e1", "e2"]


def test_read_cjk_semantic_recall() -> None:
    """中文整句检索：二元切分让相关条目胜出（旧 split() 对中文整句近零召回）。"""
    store = MemoryStore()
    store.write("L2", _entry("e1", "L2", "用户偏好用 uv 管理依赖"))
    store.write("L2", _entry("e2", "L2", "今天天气不错"))
    results = store.read("依赖管理", budget=100)
    assert results[0].id == "e1"


def test_backend_search_cjk_bigram_rank() -> None:
    """后端 search 亦按中文二元组打分：命中条目排前。"""
    backend = FileBackend()
    backend.put(_entry("e1", "L2", "季度总结报告"))
    backend.put(_entry("e2", "L2", "无关内容"))
    assert backend.search("季度")[0].id == "e1"


def test_read_budget_truncation() -> None:
    store = MemoryStore()
    store.write("L2", _entry("e1", "L2", "x" * 100))
    store.write("L2", _entry("e2", "L2", "y" * 100))
    results = store.read("", budget=1)
    assert len(results) == 1


def test_read_truncation_skips_oversized_entry() -> None:
    """超预算的条目应**跳过**而非掐断其后更小的条目（与 B5 同族）。"""
    store = MemoryStore()
    store.write("L2", _entry("e1", "L2", "a" * 40))
    store.write("L2", _entry("e2", "L2", "b" * 4000))
    store.write("L2", _entry("e3", "L2", "c" * 40))
    ids = [e.id for e in store.read("", budget=40)]
    assert "e2" not in ids, "超预算的大条目被裁剪"
    assert set(ids) == {"e1", "e3"}, "其后更小的条目未被掐断"


def test_hot_and_cold_retrieval(tmp_path) -> None:
    path = tmp_path / "mem.jsonl"
    store = MemoryStore(backend=FileBackend(path))
    store.write("L2", _entry("e1", "L2", "hello world"))
    assert [e.id for e in store.read("hello")] == ["e1"]  # 热即时
    store2 = MemoryStore(backend=FileBackend(path))  # 冷加载
    assert [e.id for e in store2.read("hello")] == ["e1"]


def test_read_degraded_on_backend_failure() -> None:
    class _FailingBackend:
        def search(self, query: str, layer: Layer | None = None) -> list[MemoryEntry]:
            raise RuntimeError("boom")

    store = MemoryStore(backend=_FailingBackend())
    assert store.read("x") == []


def test_no_action_no_write() -> None:
    store = MemoryStore()
    assert store.write("L2", _entry("e1", "L2", "x", source="")) is None
    assert store.write("L2", _entry("e2", "L2", "x", trace_id="")) is None
    assert store.index().entries == []


def test_crystallize_dissolve() -> None:
    crystallizer = Crystallizer()
    skill = _entry("skill1", "L3", "处理 CSV 的经验")
    candidate = crystallizer.crystallize(skill)
    assert candidate.plugin_id == "skill.skill1"
    assert candidate.source_entry_id == "skill1"
    lesson = crystallizer.dissolve("plugin.x")
    assert lesson.layer == "L3"
    assert "plugin.x" in lesson.content


def test_concurrent_writes_no_loss() -> None:
    store = MemoryStore()
    n = 200

    def worker(i: int) -> None:
        store.write("L2", _entry(f"e{i}", "L2", f"内容 {i}"))

    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(worker, range(n)))
    assert len(store.index().entries) == n


# ---- Phase 18 #1/#2：字段 + 多因子重排 + 语义相似（change 0039） ----


def test_memory_entry_new_fields_default_and_legacy_load(tmp_path) -> None:
    """新字段有默认值；旧 JSONL 记录（缺字段）经默认值加载，无需迁移。"""
    fresh = _entry("e1", "L2", "x")
    assert fresh.importance == 0.0
    assert fresh.kind == "episodic"

    legacy = json.dumps(
        {
            "id": "old",
            "layer": "L2",
            "content": "legacy fact",
            "tags": [],
            "source": "loop",
            "trace_id": "t",
            "reuse_count": 0,
            "ts": 1.0,
            "session_id": "",
        }
    )
    path = tmp_path / "mem.jsonl"
    path.write_text(legacy + "\n", encoding="utf-8")
    loaded = MemoryStore(backend=FileBackend(path)).read("legacy")
    assert [e.id for e in loaded] == ["old"]
    assert loaded[0].kind == "episodic" and loaded[0].importance == 0.0


def test_read_ranks_by_importance() -> None:
    """同等相似度下，importance 更高的条目排前（乘性调制）。"""
    store = MemoryStore()
    store.write("L2", _entry("low", "L2", "apple banana"))
    imp = _entry("high", "L2", "apple banana")
    imp.importance = 0.9
    store.write("L2", imp)
    assert store.read("apple banana", budget=100)[0].id == "high"


def test_read_reinforces_reuse_count() -> None:
    """read 命中即 reuse_count +1（复用即强化）。"""
    store = MemoryStore()
    store.write("L2", _entry("e1", "L2", "hello"))
    store.read("hello", budget=100)
    store.read("hello", budget=100)
    assert store.audit()[0].reuse_count == 2  # noqa: PLR2004 — 两次 read 各强化一次


def test_read_embeds_query_once_and_caches_vectors() -> None:
    """注入 embedder：query 只向量化一次，未变条目向量复用缓存。"""
    batches: list[list[str]] = []

    def embedder(texts: list[str]) -> list[list[float]]:
        batches.append(list(texts))
        return [[float(len(t)), 1.0] for t in texts]

    store = MemoryStore(embedder=embedder)
    for i in range(3):
        store.write("L2", _entry(f"e{i}", "L2", f"fact {i}"))
    store.read("query", budget=100)
    embedded = [t for batch in batches for t in batch]
    assert embedded.count("query") == 1, "每次检索 query 只向量化一次"
    assert len(embedded) == 4, "3 条内容 + 1 次 query"  # noqa: PLR2004

    before = len(batches)
    store.read("query", budget=100)  # 条目与 query 均已缓存 → 无新向量化
    assert len(batches) == before, "未变条目与 query 复用缓存，不重复向量化"


def test_read_degrades_to_lexical_when_embedder_raises() -> None:
    """embedder 抛错时降级词法，检索不中断。"""

    def embedder(texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedder down")  # noqa: TRY003 — 模拟 embedding 服务不可达

    store = MemoryStore(embedder=embedder)
    store.write("L2", _entry("e1", "L2", "apple"))
    assert [e.id for e in store.read("apple", budget=100)] == ["e1"]


def test_batch_embed_adapter() -> None:
    """单条可调用 → MemoryStore 的批量契约。"""
    batch = batch_embed(lambda t: [float(len(t))])
    assert batch(["ab", "cde"]) == [[2.0], [3.0]]
