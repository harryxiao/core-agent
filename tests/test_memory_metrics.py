"""记忆运行指标快照（change 0311 / P2-5，规格「记忆运行指标快照」）。

钉住进程内累计口径：写入按 kind、幂等重放、闸门拒收、检索注入统计、巩固耗时/失败；
并钉住两条易错边界 —— 巩固内部打分读**不**计入 recall，`reinforce=False` 零强化。
"""

from __future__ import annotations

from typing import Any

import pytest

from core.memory import MemoryEntry, MemoryStore
from core.plugin_registry import EffectTracker

_OLD_TS = 1_000.0


def _entry(  # noqa: PLR0913 — 测试工厂的显式字段
    entry_id: str = "e1",
    *,
    layer: str = "L2",
    kind: str = "episodic",
    content: str = "内容",
    ts: float = 0.0,
    trace_id: str = "",
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer=layer,  # type: ignore[arg-type] — 测试内层字面量合法
        content=content,
        tags=[],
        source="loop",
        trace_id=trace_id or f"t.{entry_id}",
        ts=ts,
        session_id="s1",
        kind=kind,
    )


class _ScoreResult:
    def __init__(self) -> None:
        self.answers = {"score": {"score": 0.9}}


class _Scorer:
    """决策打分器替身：只计数（供「内部读不计入」用例）。"""

    def __init__(self) -> None:
        self.calls = 0

    def score(self, state: dict[str, Any], entries: list[dict[str, Any]]) -> _ScoreResult:
        self.calls += 1
        return _ScoreResult()


class _SteppingClock:
    """确定性单调钟：每次调用前进 0.5 秒。"""

    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        self._now += 0.5
        return self._now


# ---- 写入面 ----


def test_writes_counted_by_kind() -> None:
    store = MemoryStore()
    store.write("L2", _entry("a", kind="episodic"))
    store.write("L2", _entry("b", kind="episodic"))
    store.write("L2", _entry("c", kind="semantic"))

    snapshot = store.metrics_snapshot()

    assert snapshot["memory.writes.episodic"] == 2  # noqa: PLR2004 — 两次同 kind 写入
    assert snapshot["memory.writes.semantic"] == 1


def test_kind_is_sanitized() -> None:
    store = MemoryStore()
    store.write("L2", _entry("a", kind="Key Fact!"))

    assert store.metrics_snapshot()["memory.writes.key_fact_"] == 1


def test_idempotent_replay_counted_as_deduped() -> None:
    store = MemoryStore()
    store.write("L2", _entry("a"))
    store.write("L2", _entry("a"))

    snapshot = store.metrics_snapshot()

    assert snapshot["memory.writes.episodic"] == 1
    assert snapshot["memory.writes.deduped"] == 1


def test_gate_rejection_counted_not_as_write() -> None:
    store = MemoryStore(importance_scorer=lambda entry: 0.0)

    with pytest.warns(RuntimeWarning):
        assert store.write("L2", _entry("a")) is None

    snapshot = store.metrics_snapshot()
    assert snapshot["memory.writes.rejected"] == 1
    assert snapshot.get("memory.writes.episodic", 0) == 0


def test_no_action_rejection_not_counted_as_rejected() -> None:
    store = MemoryStore()
    entry = _entry("a")
    entry.trace_id = ""

    assert store.write("L2", entry) is None

    snapshot = store.metrics_snapshot()
    assert snapshot["memory.writes.rejected"] == 0
    assert snapshot["memory.writes.deduped"] == 0


# ---- 检索面 ----


def test_recall_stats_accumulate() -> None:
    store = MemoryStore()
    store.write("L2", _entry("a", content="巡检 内存 水位"))
    store.write("L2", _entry("b", content="巡检 内存 水位 复核"))

    store.read("巡检 内存")
    store.read("巡检 内存", budget=1)

    snapshot = store.metrics_snapshot()
    assert snapshot["memory.recall.calls"] == 2  # noqa: PLR2004 — 两次检索
    assert snapshot["memory.recall.candidates"] == 4  # noqa: PLR2004 — 每条目各命中一次
    assert snapshot["memory.recall.injected"] >= 2  # noqa: PLR2004 — 首条无条件注入
    assert snapshot["memory.recall.injected_tokens"] > 0
    assert (
        snapshot["memory.recall.candidates"]
        == snapshot["memory.recall.injected"]
        + snapshot["memory.recall.excluded_by_budget"]
        + snapshot["memory.recall.excluded_by_diversity"]
    )


def test_internal_compaction_read_not_counted() -> None:
    """巩固内部为决策打分执行的检索不得虚增 `memory.recall.*`。"""
    scorer = _Scorer()
    store = MemoryStore(compactor=scorer)
    store.write("L2", _entry("e1"))

    store.compact(session_id="s1")

    assert scorer.calls == 1
    snapshot = store.metrics_snapshot()
    assert snapshot["memory.recall.calls"] == 0
    assert snapshot["memory.recall.candidates"] == 0


def test_reinforce_false_leaves_reuse_count_and_no_effect() -> None:
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker)
    store.write("L2", _entry("a", content="巡检 内存"))

    result = store.recall("巡检 内存", reinforce=False)

    assert result.entries[0].reuse_count == 0
    assert tracker.audit("reuse.a") == []
    assert store.metrics_snapshot()["memory.recall.calls"] == 1


def test_reinforce_default_still_increments() -> None:
    store = MemoryStore()
    store.write("L2", _entry("a", content="巡检 内存"))

    store.recall("巡检 内存")

    assert store.audit()[0].reuse_count == 1


# ---- 巩固面 ----


def test_consolidation_duration_and_failure() -> None:
    def _boom(entries: list[MemoryEntry]) -> str:
        raise RuntimeError("boom")

    store = MemoryStore(summarizer=_boom, clock=_SteppingClock())
    store.write("L2", _entry("e1", ts=_OLD_TS))

    with pytest.raises(RuntimeError):
        store.compact(session_id="s1")

    snapshot = store.metrics_snapshot()
    assert snapshot["memory.consolidation.runs"] == 1
    assert snapshot["memory.consolidation.failures"] == 1
    assert snapshot["memory.consolidation.elapsed_ms"] > 0


def test_disabled_consolidation_not_counted() -> None:
    store = MemoryStore(
        summarizer=lambda entries: "摘要", consolidation_enabled=False, clock=_SteppingClock()
    )
    store.write("L2", _entry("e1", ts=_OLD_TS))

    assert store.compact(session_id="s1") is None

    assert store.metrics_snapshot()["memory.consolidation.runs"] == 0


# ---- 快照形状 ----


def test_snapshot_has_fixed_keys() -> None:
    snapshot = MemoryStore().metrics_snapshot()

    for name in (
        "memory.writes.deduped",
        "memory.writes.rejected",
        "memory.recall.calls",
        "memory.recall.candidates",
        "memory.recall.injected",
        "memory.recall.injected_tokens",
        "memory.recall.excluded_by_budget",
        "memory.recall.excluded_by_diversity",
        "memory.consolidation.runs",
        "memory.consolidation.failures",
        "memory.consolidation.elapsed_ms",
    ):
        assert snapshot[name] == 0
    assert all(isinstance(value, float) for value in snapshot.values())


def test_snapshot_is_zero_effect() -> None:
    store = MemoryStore()
    store.write("L2", _entry("a", content="巡检 内存"))
    store.read("巡检 内存")
    before = store.metrics_snapshot()
    entries_before = [(e.id, e.reuse_count) for e in store.audit()]

    after = store.metrics_snapshot()

    assert after == before
    assert [(e.id, e.reuse_count) for e in store.audit()] == entries_before
