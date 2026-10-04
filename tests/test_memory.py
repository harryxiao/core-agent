"""memory 单元测试（对齐规格场景 + M1 验收锚点）。

覆盖：分层写入落对层 + L1 最小索引、read 相关性排序 + 预算截断、
热/冷检索 + 失败降级、无行动不写入、结晶/溶解、并发写入不丢条目。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from core.memory import (
    Crystallizer,
    FileBackend,
    Layer,
    MemoryEntry,
    MemoryStore,
)


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
