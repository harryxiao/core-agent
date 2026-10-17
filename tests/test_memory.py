"""memory 单元测试（对齐规格场景 + M1 验收锚点）。

覆盖：分层写入落对层 + L1 最小索引、read 相关性排序 + 预算截断、
热/冷检索 + 失败降级、无行动不写入、结晶/溶解、并发写入不丢条目。
"""

from __future__ import annotations

import json
import math
import time
import warnings
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

import pytest

from core.judgment import DecisionPrimitive, DecisionResult
from core.memory import (
    MAX_SUMMARY_CHARS,
    Crystallizer,
    FileBackend,
    Layer,
    MemoryEntry,
    MemoryStore,
    recency_decay,
)
from core.memory.embedding import batch_embed
from core.memory.store import (
    _GATE_EXEMPT_SOURCES,
    _IMPORTANCE_AMBIT,
    _IMPORTANCE_FLOOR,
    _decay_score,
)
from core.memory.summarize import build_prompt
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


# ---- 压实按会话收窄（change `0131` / ADR-0124，账本 E66） ----


def test_compact_scoped_to_session_leaves_others_intact() -> None:
    """`session_id` 非空 ⇒ 只聚合该会话：他会话条目层级、摘要逐字不变。"""
    store = MemoryStore(summarizer=lambda entries: "摘要：事实")
    store.write("L2", _session_entry("a0", "甲的零", "A"))
    store.write("L2", _session_entry("b0", "乙的零", "B"))
    store.write("L2", _session_entry("b1", "乙的一", "B"))

    store.compact(session_id="A")

    layers = dict(store.index().entries)
    assert layers["a0"] == "L4", "本会话条目被归档"
    assert layers["b0"] == "L2" and layers["b1"] == "L2", "他会话条目逐字不变"
    summaries = {e.id for e in store.audit() if e.kind == "semantic"}
    assert summaries == {"compaction.summary.A"}, "不跨会话提炼"


def test_compact_default_session_id_keeps_full_store_semantics() -> None:
    """缺省 `session_id=""` ⇒ 全量语义逐字不变（循环内节拍压实依赖）。"""
    store = MemoryStore(summarizer=lambda entries: "摘要：事实")
    store.write("L2", _session_entry("a0", "甲的零", "A"))
    store.write("L2", _session_entry("b0", "乙的零", "B"))

    store.compact()

    layers = dict(store.index().entries)
    assert layers["a0"] == "L4" and layers["b0"] == "L4"
    summaries = {e.id for e in store.audit() if e.kind == "semantic"}
    assert summaries == {"compaction.summary.A", "compaction.summary.B"}


def test_compact_scoped_session_scores_only_that_session() -> None:
    """收窄范围也覆盖重要度打分写回：他会话条目不被打分（value 保持原值）。"""
    scorer = _ValueScorer({"a0": 0.9, "b0": 0.9})
    store = MemoryStore(compactor=scorer, summarizer=lambda entries: "摘要：事实")
    store.write("L2", _session_entry("a0", "甲的零", "A"))
    store.write("L2", _session_entry("b0", "乙的零", "B"))

    store.compact(session_id="A")

    by_id = {e.id: e for e in store.audit()}
    assert by_id["a0"].importance == 0.9, "本会话条目被打分"  # noqa: PLR2004 — 假件给定分值
    assert by_id["b0"].importance == 0.0, "他会话条目保持原重要度（未被本轮触及）"


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


# ---- 增量滚动摘要（change 0148 / ADR-0140，账本 E90） ----


def _summary_entry(entry_id: str, content: str, session_id: str) -> MemoryEntry:
    """构造一条既有摘要条目（`tags` 带 `summary`，与 store 落库形态一致）。"""
    entry = _session_entry(entry_id, content, session_id, kind="semantic")
    entry.tags = ["compaction", "summary"]
    entry.source = "compaction"
    return entry


def test_build_prompt_renders_existing_summary_slot() -> None:
    """既有摘要条目渲染为「现有摘要」槽；无则不含该槽。"""
    prior = _summary_entry("compaction.summary.s1", "早期结论：X 已决", "s1")
    fresh = _session_entry("e1", "新增事实 Y", "s1")

    prompt = build_prompt([prior, fresh])
    assert "现有摘要" in prompt, "既有摘要须渲染为显式槽位"
    assert "早期结论：X 已决" in prompt, "既有摘要原文进入槽位"
    assert "新增事实 Y" in prompt, "新条目照常逐条渲染"

    without = build_prompt([fresh])
    assert "现有摘要" not in without, "无既有摘要 ⇒ 不渲染该槽"


def _summary_slot(prompt: str) -> str:
    """取出 prompt 中「现有摘要」槽位的正文（`_elide_summary` 的产物）。"""
    return prompt.split("现有摘要：\n", 1)[1].split("\n\n会话事件：", 1)[0]


def test_build_prompt_preserves_summary_tail_when_over_bound() -> None:
    """越界 ⇒ 首尾保留：尾部（最新结论）仍在、含中略标记、总节选 ≤ 上界（change 0193）。"""
    body = "首部结论：" + "早" * (MAX_SUMMARY_CHARS + 200)
    tail = "尾部结论：最终交付物"
    prior = _summary_entry("compaction.summary.s1", body + tail, "s1")

    prompt = build_prompt([prior, _session_entry("e1", "新增事实", "s1")])

    slot = _summary_slot(prompt)
    assert tail in slot, "尾部（最新结论）SHALL 保留，不再被头截断销毁"
    assert "中略" in slot, "越界 ⇒ 含省略标记"
    assert len(slot) <= MAX_SUMMARY_CHARS, "节选总长不超过上界（token 有界不破）"


def test_build_prompt_keeps_summary_verbatim_below_bound() -> None:
    """未越界 ⇒ 既有摘要**逐字**投喂（与变更前一致）—— 兼容性红线。"""
    content = "结论：" + "短" * 100
    prior = _summary_entry("compaction.summary.s1", content, "s1")

    prompt = build_prompt([prior, _session_entry("e1", "新增", "s1")])

    assert _summary_slot(prompt) == content, "未越界 ⇒ 逐字不变"
    assert "中略" not in prompt


def test_build_prompt_slot_stays_bounded_for_huge_summary() -> None:
    """极大既有摘要（10× 上界）⇒ 槽位仍 ≤ 上界（防 prompt 爆炸，change 0193 有界性）。"""
    prior = _summary_entry("compaction.summary.s1", "长" * (MAX_SUMMARY_CHARS * 10), "s1")

    prompt = build_prompt([prior, _session_entry("e1", "新增", "s1")])

    assert len(_summary_slot(prompt)) <= MAX_SUMMARY_CHARS


def test_compaction_warns_when_skipping_low_value_session() -> None:
    """价值闸跳过 ⇒ `warnings.warn` 留痕**只报会话键**（不回显正文，change 0193）。"""
    store = MemoryStore(compactor=_ValueScorer({"lo0": 0.1}), summarizer=lambda entries: "摘要")
    store.write("L2", _session_entry("lo0", "绝密正文勿回显", "s-lo"))

    with pytest.warns(RuntimeWarning) as rec:
        store.compact()

    text = " ".join(str(w.message) for w in rec)
    assert "s-lo" in text, "留痕报会话键"
    assert "绝密正文" not in text, "SHALL NOT 回显正文（密钥红线）"


def test_compact_feeds_existing_summary_back_to_summarizer() -> None:
    """同会话二次压实：第二次投喂材料**首元素**为该会话既有摘要条目。"""
    seen: list[list[str]] = []

    def summarizer(entries: list[MemoryEntry]) -> str:
        seen.append([e.id for e in entries])
        return "摘要：" + "；".join(e.content for e in entries)

    store = MemoryStore(summarizer=summarizer)
    store.write("L2", _session_entry("e0", "事实零", "s1"))
    store.compact()
    assert seen == [["e0"]], "首次压实无既有摘要，材料逐字为原始条目"

    store.write("L2", _session_entry("e1", "事实一", "s1"))
    store.compact()

    assert seen[1][0] == "compaction.summary.s1", "第二次投喂首元素为既有摘要条目"
    assert "e1" in seen[1], "本轮新增条目一并投喂"


def test_compact_rolling_merge_preserves_prior_conclusions() -> None:
    """轮 1 摘要结论在轮 2 压实后仍在（滚动合并，不丢早期结论）。"""
    store = MemoryStore(summarizer=lambda entries: "；".join(e.content for e in entries))
    store.write("L2", _session_entry("e0", "事实零", "s1"))
    store.compact()

    first = {e.id: e for e in store.audit()}["compaction.summary.s1"]
    assert "事实零" in first.content

    store.write("L2", _session_entry("e1", "事实一", "s1"))
    store.compact()

    merged = {e.id: e for e in store.audit()}["compaction.summary.s1"]
    assert "事实零" in merged.content, "早期结论不被静默丢弃"
    assert "事实一" in merged.content, "新增事实并入同一摘要"


def test_compact_keeps_single_summary_entry_per_session() -> None:
    """同会话连续压实：摘要条目**恰一条**、`id` 不变（滚动内容不滚动条目数）。"""
    store = MemoryStore(summarizer=lambda entries: "；".join(e.content for e in entries))
    store.write("L2", _session_entry("e0", "事实零", "s1"))
    store.compact()
    store.write("L2", _session_entry("e1", "事实一", "s1"))
    store.compact()

    summaries = [e for e in store.audit() if e.kind == "semantic" and e.session_id == "s1"]
    assert len(summaries) == 1, "每会话至多一条摘要条目"  # noqa: PLR2004 — 单一性口径
    assert summaries[0].id == "compaction.summary.s1", "摘要 id 不变"
    assert {"from:e1"} <= set(summaries[0].tags), "tags 携带本轮原条目出处"


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


# ---- 复用延缓新鲜度衰减（change 0177 / ADR-0168 / 台账 E114） ----


def test_decay_score_unchanged_when_never_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    """`reuse_count=0` ⇒ 复用调制退化为恒等：评分与调制前公式**逐字一致**（零回归锚点）。

    冻结 ``time.time`` 以消除 ``recency_decay`` 内部取时刻的抖动（否则两次调用差在微秒级）。
    """
    fixed = 1_700_000_000.0
    monkeypatch.setattr(time, "time", lambda: fixed)
    entry = _entry("e", "L2", "陈旧")
    entry.kind = "episodic"
    entry.ts = fixed - 30 * 86400.0
    legacy = recency_decay(entry) * (1.0 + math.log1p(entry.reuse_count)) * (1.0 + entry.importance)
    assert _decay_score(entry) == legacy


def test_decay_score_rises_with_reuse() -> None:
    """同时间戳、同 importance 下，复用过的条目评分更高（衰减被延缓）。"""
    plain = _aged(_session_entry("plain", "陈旧", "s1"), 30)
    reused = _aged(_session_entry("reused", "陈旧", "s1"), 30)
    reused.reuse_count = 3

    assert _decay_score(reused) > _decay_score(plain)


def test_forget_spares_reused_entry_over_identical_plain_one() -> None:
    """同陈旧度下未被复用的条目被归档，复用过的层级不变（Scenario「复用延缓新鲜度衰减」）。"""
    store = MemoryStore()
    store.write("L2", _aged(_session_entry("plain", "陈旧", "s1"), 30))
    reused = _aged(_session_entry("reused", "陈旧", "s1"), 30)
    reused.reuse_count = 3
    store.write("L2", reused)

    assert store.forget() == ["plain"]
    assert dict(store.index().entries)["reused"] == "L2", "复用延缓衰减 ⇒ 未过阈值、层级不变"


def test_decay_score_slows_freshness_decay_by_reuse(monkeypatch: pytest.MonkeyPatch) -> None:
    """r>0 ⇒ 新鲜度项被**幂调制**抬高：评分**高于**旧公式「纯时间新鲜度 × 复用因子」。"""
    fixed = 1_700_000_000.0
    monkeypatch.setattr(time, "time", lambda: fixed)
    entry = _entry("e", "L2", "陈旧")
    entry.kind = "episodic"
    entry.ts = fixed - 30 * 86400.0
    entry.reuse_count = 3
    old = recency_decay(entry) * (1.0 + math.log1p(entry.reuse_count)) * (1.0 + entry.importance)
    assert _decay_score(entry) > old


def test_forget_spares_reused_entry_that_plain_decay_would_archive() -> None:
    """**判别性**用例：99 天陈旧 + `reuse_count=1` 在旧公式下会被归档，复用调制后越阈值留存。

    纯时间新鲜度 ≈0.01 ⇒ 旧评分 ≈0.017（< 0.05 阈值）；调制后 ≈0.11（≥ 阈值）。
    """
    store = MemoryStore()
    reused = _aged(_session_entry("reused", "陈旧", "s1"), 99)
    reused.reuse_count = 1
    store.write("L2", reused)

    assert store.forget() == [], "复用延缓衰减 ⇒ 越阈值留存（旧公式会归档）"


# ---- 写入侧重要度闸门（change 0177 / ADR-0168 / 台账 E114） ----


def _scorer(value: float) -> Callable[[MemoryEntry], float]:
    return lambda entry: value


def test_gate_unwired_write_is_unchanged() -> None:
    """未注入 scorer ⇒ 写入与现状逐字一致：不评分、不拒收、不降层、不动 importance、无留痕。"""
    store = MemoryStore()
    entry = _entry("e1", "L2", "事实")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert store.write("L2", entry) == "e1"
    assert store.index().entries == [("e1", "L2")]
    assert entry.importance == 0.0, "不写 importance"
    assert caught == [], "无留痕"


def test_gate_rejects_low_score_entry() -> None:
    """低于 FLOOR ⇒ 拒收：不落库、无效应记录、留痕（Scenario「低分条目拒收」）。"""
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker, importance_scorer=_scorer(_IMPORTANCE_FLOOR - 0.1))

    with pytest.warns(RuntimeWarning, match="importance gate"):
        assert store.write("L2", _entry("e1", "L2", "低价值")) is None

    assert store.audit() == [], "不落库"
    assert tracker.rollback().reverted == [], "无效应记录"


def test_gate_middle_score_downgrades_to_l4_reversibly() -> None:
    """[FLOOR, AMBIT) ⇒ 降层 L4，且回滚降层即按原意向层恢复（Scenario「中间分降层写入」）。"""
    tracker = EffectTracker()
    mid = (_IMPORTANCE_FLOOR + _IMPORTANCE_AMBIT) / 2
    store = MemoryStore(effect_tracker=tracker, importance_scorer=_scorer(mid))
    store.write("L2", _entry("e1", "L2", "中间价值"))

    assert dict(store.index().entries)["e1"] == "L4", "降层归档"
    assert tracker.rollback("gate.e1").undo_failed == []
    assert dict(store.index().entries)["e1"] == "L2", "回滚降层 ⇒ 迁回意向层"


def test_gate_high_score_keeps_layer_and_writes_back_importance() -> None:
    """≥ AMBIT ⇒ 按意向层入库且 importance 写为分值；写入 + 写回两效应均可撤销。"""
    tracker = EffectTracker()
    high = _IMPORTANCE_AMBIT + 0.1
    store = MemoryStore(effect_tracker=tracker, importance_scorer=_scorer(high))
    store.write("L2", _entry("e1", "L2", "高价值"))

    assert dict(store.index().entries)["e1"] == "L2"
    assert store.audit("t")[0].importance == high, "importance 写为分值"

    report = tracker.rollback("t")

    assert report.undo_failed == []
    assert len(report.reverted) == 2, "写入 + 写回两效应均可撤销"  # noqa: PLR2004
    assert store.audit("t") == [], "回滚 ⇒ 条目移除"


def test_gate_scorer_error_degrades_to_normal_write() -> None:
    """scorer 抛错 ⇒ 降级放行：按意向层正常入库、留痕、不中断（Scenario「评分器抛错降级放行」）。"""

    def boom(entry: MemoryEntry) -> float:
        raise RuntimeError("scorer down")  # noqa: TRY003 — 测试替身，消息无对外契约

    store = MemoryStore(importance_scorer=boom)
    with pytest.warns(RuntimeWarning, match="scorer"):
        assert store.write("L2", _entry("e1", "L2", "x")) == "e1"

    assert dict(store.index().entries)["e1"] == "L2"
    assert store.audit("t")[0].importance == 0.0, "不写 importance"


def test_gate_out_of_range_score_degrades_to_normal_write() -> None:
    """scorer 返回界外值 ⇒ 降级放行（不拒收、不降层），留痕。"""
    store = MemoryStore(importance_scorer=_scorer(1.5))

    with pytest.warns(RuntimeWarning, match="out-of-range"):
        assert store.write("L2", _entry("e1", "L2", "x")) == "e1"

    assert dict(store.index().entries)["e1"] == "L2"


# ---- 闸门内部产物豁免面（change 0181 / ADR-0172 / 台账 E118） ----


def test_gate_exempt_face_is_the_pipeline_sources() -> None:
    """豁免面即系统管道派生产物 —— 新增派生来源须同步登记（漏登记 ⇔ 该来源被评分）。

    `relation` 于 change 0203 登记：关系三元组与关键事实同属压实期派生产物
    （`source="relation"`，见「实体关系抽取（relations）」）。`episodic` 于 change 0241
    登记：情景归纳结论同为派生结论（`source="episodic"`，见「情景归纳」）。
    """
    assert (
        frozenset({"compaction", "context", "extraction", "relation", "episodic"})
        == _GATE_EXEMPT_SOURCES
    )


@pytest.mark.parametrize("source", sorted(_GATE_EXEMPT_SOURCES))
def test_gate_exempts_internal_derived_sources(source: str) -> None:
    """派生/内部产物不经评分：恒低分下仍按意向层入库、不降层、不写 importance、无留痕。"""
    store = MemoryStore(importance_scorer=_scorer(_IMPORTANCE_FLOOR - 0.1))
    entry = _entry("e1", "L2", "派生结论", source=source)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert store.write("L2", entry) == "e1"

    assert dict(store.index().entries)["e1"] == "L2", "不降层"
    assert entry.importance == 0.0, "不写 importance"
    assert caught == [], "豁免 ⇒ 无评分留痕"


def test_gate_exempt_face_does_not_cover_organic_writes() -> None:
    """豁免面只覆盖系统派生产物：来源非豁免面（loop）仍受评分 ⇒ 恒低分下拒收 + 留痕。"""
    store = MemoryStore(importance_scorer=_scorer(_IMPORTANCE_FLOOR - 0.1))

    with pytest.warns(RuntimeWarning, match="importance gate"):
        assert store.write("L2", _entry("e1", "L2", "轨迹", source="loop")) is None

    assert store.audit() == []


# ---- summary_for：按会话读取既有摘要（只读；change 0150 / ADR-0142 / 账本 E94）----


def test_summary_for_returns_session_summary_entry() -> None:
    store = MemoryStore(summarizer=lambda entries: "摘要：事实")
    store.write("L2", _session_entry("e0", "事实零", "s1"))
    store.write("L2", _session_entry("e1", "事实一", "s1"))
    store.compact()

    found = store.summary_for("s1")

    assert found is not None
    assert found.id == "compaction.summary.s1"
    assert found.kind == "semantic" and found.source == "compaction"
    assert "summary" in found.tags
    assert store.summary_for("other") is None, "无该会话摘要 ⇒ None"


def test_summary_for_default_session_key() -> None:
    store = MemoryStore(summarizer=lambda entries: "摘要：事实")
    store.write("L2", _session_entry("e0", "无归属事实", ""))

    store.compact()

    found = store.summary_for("")
    assert found is not None and found.id == "compaction.summary.default"


def test_summary_for_is_read_only() -> None:
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker, summarizer=lambda entries: "摘要：事实")
    store.write("L2", _session_entry("e0", "事实零", "s1"))
    store.compact()

    before = [(e.id, e.layer, e.reuse_count, e.importance) for e in store.audit()]
    effects_before = len(tracker.audit("compaction.s1"))

    first = store.summary_for("s1")
    second = store.summary_for("s1")

    after = [(e.id, e.layer, e.reuse_count, e.importance) for e in store.audit()]
    assert before == after, "读取不改条目（无写入、不动 reuse_count/importance/层）"
    assert len(tracker.audit("compaction.s1")) == effects_before, "读取不记效应"
    assert first is not None and second is not None and first.id == second.id


def test_summary_for_none_without_summarizer() -> None:
    store = MemoryStore()
    store.write("L2", _session_entry("e0", "事实零", "s1"))
    store.compact()

    assert store.summary_for("s1") is None, "未注入摘要器 ⇒ 未写摘要 ⇒ None"


# ---- 中层摘要：会话滑窗的中带物化（change 0178 / ADR-0169 / 台账 E115） ----


def _stub(entry_id: str, content: str, session_id: str = "s1") -> MemoryEntry:
    """中带**转录桩**：prompt-only 的临时条目（不进库、不当来源迁移）。"""
    return _session_entry(entry_id, content, session_id)


def test_summarize_slice_rolls_merge_prior_mid_summary() -> None:
    """滚动合并：既有中层摘要作材料**首条**（同 `_summarize_sessions` 形态）。"""
    seen: list[list[str]] = []

    def summarizer(entries: list[MemoryEntry]) -> str:
        seen.append([e.id for e in entries])
        return "中层摘要：" + "；".join(e.content for e in entries)

    store = MemoryStore(summarizer=summarizer)
    store.summarize_slice("s1", [_stub("t0", "转录零")], max_chars=1000)
    store.summarize_slice("s1", [_stub("t1", "转录一")], max_chars=1000)

    assert seen[0] == ["t0"], "首批材料无既有中层摘要"
    assert seen[1] == ["compaction.mid.s1", "t1"], "既有中层摘要作首条材料滚合并"


def test_summarize_slice_unwired_summarizer_returns_none_and_writes_nothing() -> None:
    """摘要器 UNWIRED ⇒ ``None``、零写入、零效应。"""
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker)

    result = store.summarize_slice("s1", [_stub("t0", "转录零")], max_chars=1000)

    assert result is None
    assert store.audit() == [], "未注入摘要器 ⇒ 无写入"
    assert tracker.audit("compaction.mid.s1") == [], "未注入摘要器 ⇒ 无效应"


@pytest.mark.parametrize("max_chars", [0, -1])
def test_summarize_slice_nonpositive_max_chars_returns_none(max_chars: int) -> None:
    store = MemoryStore(summarizer=lambda entries: "中层摘要")
    assert store.summarize_slice("s1", [_stub("t0", "转录零")], max_chars=max_chars) is None


def test_summarize_slice_empty_entries_returns_none() -> None:
    store = MemoryStore(summarizer=lambda entries: "中层摘要")
    assert store.summarize_slice("s1", [], max_chars=1000) is None


def test_summarize_slice_does_not_migrate_source_entries() -> None:
    """**不迁移**：来源条目层级逐字不变（与 `_commit_summary` 相异）。"""
    store = MemoryStore(summarizer=lambda entries: "中层摘要")
    source = _session_entry("e0", "事实零", "s1")
    store.write("L2", source)

    store.summarize_slice("s1", [source], max_chars=1000)

    layers = dict(store.index().entries)
    assert layers["e0"] == "L2", "中层摘要 SHALL NOT 迁移来源条目"
    assert layers["compaction.mid.s1"] == "L2"


def test_summarize_slice_bounded_by_max_chars_and_redacted() -> None:
    """产物有界于 ``max_chars`` 且写前 ``redact_secrets``（密钥形态不落库）。"""
    secret = "sk-" + "a" * 20
    store = MemoryStore(summarizer=lambda entries: f"用 {secret} 走过 " + "长" * 500)

    content = store.summarize_slice("s1", [_stub("t0", "转录零")], max_chars=50)

    assert content is not None
    assert len(content) <= 50, "产物受 `max_chars` 有界"  # noqa: PLR2004 — 即传入的 max_chars
    assert secret not in content, "写前脱敏：密钥形态不落库"
    assert "<redacted>" in content
    assert store.mid_summary_for("s1").content == content  # type: ignore[union-attr]


def test_summarize_slice_reversible_by_trace() -> None:
    """效应 ``trace_id=f"compaction.mid.<key>"`` ⇒ 可整条回滚。"""
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker, summarizer=lambda entries: "中层摘要")
    store.summarize_slice("s1", [_stub("t0", "转录零")], max_chars=1000)
    assert "compaction.mid.s1" in dict(store.index().entries)

    report = tracker.rollback("compaction.mid.s1")

    assert report.undo_failed == []
    assert "compaction.mid.s1" not in dict(store.index().entries), "回滚 → 中层摘要条目被移除"


def test_mid_summary_for_is_read_only() -> None:
    """读取不改条目、不记效应（口径同 `summary_for`）。"""
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker, summarizer=lambda entries: "中层摘要")
    store.summarize_slice("s1", [_stub("t0", "转录零")], max_chars=1000)

    before = [(e.id, e.layer, e.reuse_count, e.importance) for e in store.audit()]
    effects_before = len(tracker.audit("compaction.mid.s1"))

    first = store.mid_summary_for("s1")
    second = store.mid_summary_for("s1")

    after = [(e.id, e.layer, e.reuse_count, e.importance) for e in store.audit()]
    assert before == after, "读取不改条目"
    assert len(tracker.audit("compaction.mid.s1")) == effects_before, "读取不记效应"
    assert first is not None and second is not None and first.id == second.id


def test_mid_summary_for_isolated_per_session() -> None:
    store = MemoryStore(summarizer=lambda entries: "中层摘要")
    store.summarize_slice("s1", [_stub("t0", "转录零")], max_chars=1000)

    assert store.mid_summary_for("s1") is not None
    assert store.mid_summary_for("s2") is None, "按会话隔离（他会话无中层摘要）"


# ---- 失败经验的独立沉淀面：失败条目不被压实吸收（change 0179 / ADR-0170 / 台账 E116） ----


def _failure_entry(entry_id: str, content: str, session_id: str) -> MemoryEntry:
    """轮级失败条目（loop 侧写入形态：`tags=["loop","failure"]`）。"""
    entry = _session_entry(entry_id, content, session_id)
    entry.tags = ["loop", "failure"]
    return entry


def test_compact_skips_failure_entries_but_archives_plain_ones() -> None:
    """压实材料排除带 `failure` 标签的条目：不被摘要吸收、不被迁 L4；同批普通条目照常迁 L4。"""
    seen: list[list[str]] = []

    def summarizer(entries: list[MemoryEntry]) -> str:
        seen.append([e.id for e in entries])
        return "摘要：" + "；".join(e.content for e in entries)

    store = MemoryStore(summarizer=summarizer)
    store.write("L2", _session_entry("e0", "普通事实", "s1"))
    store.write("L2", _failure_entry("loop.failure.t1", "失败：LOOP_LIMIT_EXCEEDED", "s1"))

    store.compact()

    assert seen == [["e0"]], "失败条目不入压实材料（打分/摘要/关键事实同一材料源）"
    layers = dict(store.index().entries)
    assert layers["loop.failure.t1"] == "L2", "失败条目不随压实迁 L4"
    assert layers["e0"] == "L4", "同批普通条目照常迁 L4"
    summary = next(e for e in store.audit() if e.id == "compaction.summary.s1")
    assert summary.tags == ["compaction", "summary", "from:e0"], "摘要 tags 不含失败条目 id"


def test_forget_does_not_spare_failure_entries() -> None:
    """`forget` **不豁免**失败条目：陈旧且零复用 ⇒ 仍迁 L4（失败面有界）。"""
    store = MemoryStore()
    store.write("L2", _aged(_failure_entry("loop.failure.t1", "失败：终止动作未达成", "s1"), 30))

    assert store.forget() == ["loop.failure.t1"]
    assert dict(store.index().entries)["loop.failure.t1"] == "L4", "压实豁免 ≠ 遗忘豁免"


def test_failure_entry_is_readable() -> None:
    """失败条目照常参与检索（`rank` / `_decay_score` 不看 tags ⇒ 压实豁免零排序副作用）。"""
    store = MemoryStore()
    store.write("L2", _failure_entry("loop.failure.t1", "失败：终止动作未达成", "s1"))
    store.write("L2", _session_entry("e0", "今天天气不错", "s1"))

    assert [e.id for e in store.read("终止动作未达成")][0] == "loop.failure.t1"


# ---------------------------------------------------------------------------
# 复用强化落盘（change 0187 / ADR-0178 / 台账 E124）
# ---------------------------------------------------------------------------


class _PutCountingBackend(FileBackend):
    """计数 ``put`` 的 ``FileBackend``（``path=None`` ⇒ 纯内存，无磁盘副作用）。"""

    def __init__(self) -> None:
        super().__init__()
        self.puts: list[str] = []

    def put(self, entry: MemoryEntry) -> str:
        self.puts.append(entry.id)
        return super().put(entry)


def test_reuse_reinforcement_survives_reload(tmp_path: Path) -> None:
    """命中强化**落盘**：同一后端重装（模拟进程重启）后 `reuse_count` 保持强化值。"""
    path = tmp_path / "mem.jsonl"
    store = MemoryStore(backend=FileBackend(path))
    store.write("L2", _entry("e1", "L2", "hello"))

    store.read("hello", budget=100)

    reloaded = MemoryStore(backend=FileBackend(path))
    assert reloaded.audit()[0].reuse_count == 1, "跨会话保留强化（非退回 0）"


def test_read_without_hit_records_no_write() -> None:
    """**未命中**不写（回归锚）：无候选 ⇒ 零 `put`、零效应 —— 强化只发生在命中路径上。"""
    tracker = EffectTracker()
    backend = _PutCountingBackend()
    store = MemoryStore(backend=backend, effect_tracker=tracker)

    assert store.read("什么都没有", budget=100) == []
    assert backend.puts == [], "未命中不落盘"
    assert tracker.rollback().reverted == [], "未命中不记效应"


def test_reuse_writeback_is_reversible(tmp_path: Path) -> None:
    """写回记**可撤销效应**：`rollback("reuse.<id>")` ⇒ 还原为强化**前**的值（非自减）。"""
    path = tmp_path / "mem.jsonl"
    tracker = EffectTracker()
    backend = FileBackend(path)
    store = MemoryStore(backend=backend, effect_tracker=tracker)
    store.write("L2", _entry("e1", "L2", "hello"))
    store.read("hello", budget=100)
    store.read("hello", budget=100)
    assert backend.search("")[0].reuse_count == 2  # noqa: PLR2004 — 两次 read 各强化一次

    report = tracker.rollback("reuse.e1")

    assert report.undo_failed == []
    assert backend.search("")[0].reuse_count == 0, "还原为强化前的值"
    assert FileBackend(path).search("")[0].reuse_count == 0, "还原同样落盘"


def test_only_selected_entries_are_reinforced(tmp_path: Path) -> None:
    """写放大**有界**：预算只容一条 ⇒ 仅被 `_truncate` 选中的条目落盘强化，落选候选不变。"""
    tracker = EffectTracker()
    backend = FileBackend(tmp_path / "mem.jsonl")
    store = MemoryStore(backend=backend, effect_tracker=tracker)
    store.write("L2", _entry("hot", "L2", "alpha " * 50))
    store.write("L2", _entry("cold", "L2", "beta " * 50))

    selected = store.read("alpha beta", budget=60)

    assert len(selected) == 1, "预算只容一条（两条各 75 token，第二条被跳过）"
    chosen = selected[0].id
    other = "cold" if chosen == "hot" else "hot"
    counts = {e.id: e.reuse_count for e in backend.search("")}
    assert counts[chosen] == 1, "选中条目被强化"
    assert counts[other] == 0, "落选候选不被强化（写放大有界）"
    assert len(tracker.audit(f"reuse.{chosen}")) == 1
    assert tracker.audit(f"reuse.{other}") == []
