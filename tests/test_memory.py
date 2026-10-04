"""memory 单元测试（对齐规格场景 + M1 验收锚点）。

覆盖：分层写入落对层 + L1 最小索引、read 相关性排序 + 预算截断、
热/冷检索 + 失败降级、无行动不写入、结晶/溶解、并发写入不丢条目。
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from core.judgment import DecisionPrimitive, DecisionResult
from core.memory import (
    Crystallizer,
    FileBackend,
    Layer,
    MemoryEntry,
    MemoryStore,
)
from core.memory.embedding import batch_embed
from core.plugin_registry import EffectTracker


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


# ---- 摘要式压实（0041） ----


def _session_entry(
    entry_id: str,
    content: str,
    session_id: str,
    *,
    kind: Literal["episodic", "semantic"] = "episodic",
) -> MemoryEntry:
    entry = _entry(entry_id, "L2", content)
    entry.session_id = session_id
    entry.kind = kind
    return entry


class _FakeScorer:
    """仅评分（judgment score 原语）的假件：验证「无摘要器 → 只评分不写」。"""

    def __init__(self) -> None:
        self.calls = 0

    def score(self, state, items, threshold=None):
        self.calls += 1
        return DecisionResult(primitive=DecisionPrimitive.SCORE, answers={}, fallback=False)


def test_compact_summarizes_each_session_and_archives() -> None:
    seen: list[list[str]] = []

    def summarizer(entries: list[MemoryEntry]) -> str:
        seen.append([e.id for e in entries])
        return "摘要：" + "；".join(e.content for e in entries)

    store = MemoryStore(summarizer=summarizer)
    store.write("L2", _session_entry("e0", "事实零", "s1"))
    store.write("L2", _session_entry("e1", "事实一", "s1"))
    store.write("L2", _session_entry("e2", "别的会话", "s2"))

    assert store.compact() is None, "未注入 judgment Compactor → 无评分决策返回"
    assert seen == [["e0", "e1"], ["e2"]], "按 session_id 分组，组内保持写入序"

    layers = dict(store.index().entries)
    assert layers["e0"] == "L4" and layers["e1"] == "L4", "原条目迁 L4 归档而非删除"
    assert layers["e2"] == "L4"
    summaries = {e.id: e for e in store.audit() if e.kind == "semantic"}
    assert set(summaries) == {"compaction.summary.s1", "compaction.summary.s2"}
    s1 = summaries["compaction.summary.s1"]
    assert s1.layer == "L2" and s1.source == "compaction"
    assert s1.trace_id == "compaction.s1"
    assert {"from:e0", "from:e1"} <= set(s1.tags), "tags 携带原始条目 id 出处"


def test_compact_without_summarizer_only_scores() -> None:
    scorer = _FakeScorer()
    store = MemoryStore(compactor=scorer)
    store.write("L2", _session_entry("e0", "事实零", "s1"))

    decision = store.compact("事实", budget=100)

    assert scorer.calls == 1
    assert decision is not None and decision.primitive is DecisionPrimitive.SCORE
    assert dict(store.index().entries)["e0"] == "L2", "无摘要器 → 原条目层级不变"
    assert [e for e in store.audit() if e.kind == "semantic"] == [], "无摘要器 → 不写摘要条目"


def test_compact_is_reversible_by_trace() -> None:
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker, summarizer=lambda entries: "摘要：事实")
    store.write("L2", _session_entry("e0", "事实零", "s1"))
    store.write("L2", _session_entry("e1", "事实一", "s1"))

    store.compact()
    assert dict(store.index().entries)["e0"] == "L4"

    report = tracker.rollback("compaction.s1")

    assert report.undo_failed == []
    layers = dict(store.index().entries)
    assert layers["e0"] == "L2" and layers["e1"] == "L2", "回滚 → 原条目迁回原层"
    assert "compaction.summary.s1" not in layers, "回滚 → 摘要条目被移除"


def test_compact_summary_outranks_archived_originals() -> None:
    """归档原文仍可检索，但 L2 摘要优先级更高（L2 0.6 > L4 0.2）。"""

    def summarizer(entries: list[MemoryEntry]) -> str:
        return "事实"

    store = MemoryStore(summarizer=summarizer)
    store.write("L2", _session_entry("e0", "事实", "s1"))

    store.compact()

    ids = [e.id for e in store.read("事实", budget=100)]
    assert ids[0] == "compaction.summary.s1"
    assert "e0" in ids


# ---- 固化与遗忘（0042） ----


class _ValueScorer:
    """按条目 id 查表返回分值的假 scorer（judgment score 原语：条目集单一分数）。"""

    def __init__(self, scores: dict[str, float], *, error: bool = False) -> None:
        self._scores = scores
        self._error = error
        self.calls: list[list[str]] = []

    def score(self, state, items, threshold=None):
        self.calls.append([item["id"] for item in items])
        if self._error:
            raise RuntimeError("judge unavailable")  # noqa: TRY003 — 假件模拟决策服务不可达
        return DecisionResult(
            primitive=DecisionPrimitive.SCORE,
            answers={
                "score": {
                    "score": self._scores.get(items[0]["id"], 0.0),
                    "legend": "",
                    "probabilities": {},
                    "confidence": 1.0,
                }
            },
            fallback=False,
        )


def _aged(entry: MemoryEntry, days: float) -> MemoryEntry:
    """把条目时间戳回拨 ``days`` 天（遗忘评分的时间维度）。"""
    entry.ts = time.time() - days * 86400.0
    return entry


def test_compact_scores_importance_per_entry_and_rollback_restores() -> None:
    tracker = EffectTracker()
    scorer = _ValueScorer({"e0": 0.9, "e1": 0.8})
    store = MemoryStore(effect_tracker=tracker, compactor=scorer, summarizer=lambda entries: "摘要")
    store.write("L2", _session_entry("e0", "重要事实", "s1"))
    store.write("L2", _session_entry("e1", "次要事实", "s1"))

    store.compact()

    by_id = {e.id: e for e in store.audit()}
    assert by_id["e0"].importance == 0.9, "分值写回条目"  # noqa: PLR2004 — 假件给定分值
    assert by_id["e1"].importance == 0.8  # noqa: PLR2004 — 假件给定分值
    per_entry = [call[0] for call in scorer.calls if len(call) == 1]
    assert sorted(per_entry) == ["e0", "e1"], "score 原语为整集分数 → 逐条目一次调用"

    report = tracker.rollback("compaction.s1")

    assert report.undo_failed == []
    restored = {e.id: e for e in store.audit()}
    assert restored["e0"].importance == 0.0, "回滚 → importance 恢复旧值"


def test_compact_value_gate_skips_low_value_session() -> None:
    seen: list[list[str]] = []

    def summarizer(entries: list[MemoryEntry]) -> str:
        seen.append([e.id for e in entries])
        return "摘要"

    store = MemoryStore(compactor=_ValueScorer({"hi0": 0.9, "lo0": 0.1}), summarizer=summarizer)
    store.write("L2", _session_entry("hi0", "高价值决策", "s-hi"))
    store.write("L2", _session_entry("lo0", "寒暄一轮", "s-lo"))

    store.compact()

    assert seen == [["hi0"]], "仅达标会话进入提炼"
    layers = dict(store.index().entries)
    assert layers["hi0"] == "L4" and layers["compaction.summary.s-hi"] == "L2"
    assert layers["lo0"] == "L2", "低价值会话保留 episodic 原层"
    assert "compaction.summary.s-lo" not in layers


def test_compact_without_scorer_does_not_gate() -> None:
    """未注入 scorer：价值门槛不生效（0041 行为保持，会话全部提炼）。"""
    seen: list[list[str]] = []

    def summarizer(entries: list[MemoryEntry]) -> str:
        seen.append([e.id for e in entries])
        return "摘要"

    store = MemoryStore(summarizer=summarizer)
    store.write("L2", _session_entry("e0", "事实", "s1"))
    store.write("L2", _session_entry("e1", "别的会话", "s2"))

    store.compact()

    assert seen == [["e0"], ["e1"]]


def test_scorer_failure_keeps_importance_and_does_not_gate() -> None:
    """打分失败 ≠ 打 0 分：保持原值、不设门槛、不中断固化（决策服务抖动不致记忆停摆）。"""
    store = MemoryStore(compactor=_ValueScorer({}, error=True), summarizer=lambda entries: "摘要")
    store.write("L2", _session_entry("e0", "事实", "s1"))

    store.compact()

    entries = {e.id: e for e in store.audit()}
    assert entries["e0"].importance == 0.0, "打分失败保持原值而非写 0"
    assert "compaction.summary.s1" in entries, "打分不可得 → 不设门槛，固化流程继续"


def test_forget_archives_only_stale_low_value_l2_episodic() -> None:
    store = MemoryStore()
    stale = _aged(_session_entry("stale", "陈旧且从未复用", "s1"), 30)
    warm = _aged(_session_entry("warm", "陈旧但常复用", "s1"), 30)
    warm.reuse_count = 10
    priceless = _aged(_session_entry("priceless", "陈旧但重要", "s1"), 30)
    priceless.importance = 1.0
    fact = _aged(_session_entry("fact", "提炼事实", "s1", kind="semantic"), 30)
    for entry in (stale, warm, priceless, fact):
        store.write("L2", entry)
    store.write("L0", _aged(_entry("persona", "L0", "人格"), 30))
    store.write("L3", _aged(_entry("skill", "L3", "技能"), 30))

    forgotten = store.forget()

    assert forgotten == ["stale"], "返回被归档条目 id（撤销句柄）"
    layers = dict(store.index().entries)
    assert layers["stale"] == "L4", "低分条目迁 L4 归档而非删除"
    assert layers["warm"] == "L2" and layers["priceless"] == "L2", "高复用 / 高重要度不遗忘"
    assert layers["fact"] == "L2", "semantic 提炼产物不参与衰减"
    assert layers["persona"] == "L0" and layers["skill"] == "L3", "L0 人格 / L3 技能不遗忘"
    assert "stale" in {e.id for e in store.audit()}, "归档条目仍可 audit 追溯"


def test_forget_leaves_fresh_entries_alone() -> None:
    store = MemoryStore()
    store.write("L2", _session_entry("fresh", "刚写的事实", "s1"))

    assert store.forget() == []
    assert dict(store.index().entries)["fresh"] == "L2"


def test_forget_is_reversible_by_trace() -> None:
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker)
    store.write("L2", _aged(_session_entry("stale", "陈旧", "s1"), 30))

    assert store.forget() == ["stale"]
    assert dict(store.index().entries)["stale"] == "L4"

    report = tracker.rollback("forgetting.stale")

    assert report.undo_failed == []
    assert dict(store.index().entries)["stale"] == "L2", "按 trace 回滚 → 迁回原层"
