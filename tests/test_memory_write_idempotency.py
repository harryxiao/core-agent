"""写入幂等重放（change 0306 / ADR-0296）。

逻辑 id 稳定只能保证「重复投递不产生重复条目」；同一条写入被重放时，既有实现仍会覆盖并
重置 ``reuse_count``、刷新 ``ts``、重复记 ``memory.write`` 效应、重复通知观察者、重复评分。
本文件按规格 ADDED「写入的幂等重放」逐条锚定语义载荷相同 ⇒ 零副作用。
"""

from __future__ import annotations

from core.loop import DefaultLoop
from core.memory import MemoryEntry, MemoryStore
from core.plugin_registry import Effect, EffectTracker

_TRACE = "t1"


def _entry(
    entry_id: str = "e1",
    content: str = "巡检 甲",
    *,
    tags: list[str] | None = None,
    session_id: str = "",
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=tags if tags is not None else ["巡检"],
        source="loop",
        trace_id=_TRACE,
        session_id=session_id,
    )


def _writes(tracker: EffectTracker, trace_id: str) -> list[Effect]:
    return [effect for effect in tracker.audit(trace_id) if effect.op == "memory.write"]


def test_identical_replay_keeps_evidence_and_timestamp() -> None:
    """同载荷重放：单条、复用证据与时间戳保留、写入效应数不增。"""
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker)
    store.write("L2", _entry())
    store.read("巡检", budget=4096)  # 强化 reuse_count
    before = next(entry for entry in store.audit() if entry.id == "e1")
    reuse_before = before.reuse_count
    ts_before = before.ts
    effects_before = len(_writes(tracker, _TRACE))

    assert store.write("L2", _entry()) == "e1"

    after = next(entry for entry in store.audit() if entry.id == "e1")
    assert len(store.audit()) == 1
    assert reuse_before > 0
    assert after.reuse_count == reuse_before
    assert after.ts == ts_before
    assert len(_writes(tracker, _TRACE)) == effects_before


def test_replay_does_not_notify_observer() -> None:
    """重放不触发 ``write_observer``（观察方按一次写入一次通知实现）。"""
    seen: list[str] = []
    store = MemoryStore(write_observer=lambda _layer, entry: seen.append(entry.id))  # noqa: ARG005 — 只记 id
    store.write("L2", _entry())
    store.write("L2", _entry())
    assert seen == ["e1"]


def test_replay_does_not_rescore() -> None:
    """注入评分器时重放不二次评分（评分是真实模型成本）。"""
    calls: list[str] = []

    def scorer(entry: MemoryEntry) -> float:
        calls.append(entry.id)
        return 0.9

    store = MemoryStore(importance_scorer=scorer)
    store.write("L2", _entry())
    store.write("L2", _entry())
    assert calls == ["e1"]


def test_changed_payload_still_overwrites() -> None:
    """同 id 不同正文或标签 ⇒ 正常覆盖，并记新的写入效应（不误判为重放）。"""
    tracker = EffectTracker()
    store = MemoryStore(effect_tracker=tracker)
    store.write("L2", _entry(content="巡检 甲"))
    store.write("L2", _entry(content="巡检 乙"))
    store.write("L2", _entry(content="巡检 乙", tags=["巡检", "复检"]))

    [entry] = store.audit()
    assert entry.content == "巡检 乙"
    assert entry.tags == ["巡检", "复检"]
    assert len(_writes(tracker, _TRACE)) == 3  # noqa: PLR2004 — 三次写入各一次效应


def test_same_content_different_ids_are_distinct() -> None:
    """幂等键是逻辑 id，不是正文：不同 id 的同文条目各自成条。"""
    store = MemoryStore()
    store.write("L2", _entry(entry_id="a", content="巡检 甲"))
    store.write("L2", _entry(entry_id="b", content="巡检 甲"))
    assert sorted(entry.id for entry in store.audit()) == ["a", "b"]


def test_remember_and_compact_replay_do_not_proliferate() -> None:
    """同 trace 重放 ``remember``、同会话重放 ``compact`` ⇒ 条目与写入效应均不增。"""
    tracker = EffectTracker()
    store = MemoryStore(
        effect_tracker=tracker,
        summarizer=lambda _entries: "摘要：固定",  # noqa: ARG005 — 固定摘要用于制造同载荷
    )
    loop = DefaultLoop(memory=store)
    trajectory = [{"round": 1, "ok": True, "reply": "结论 甲"}]

    loop.remember(_TRACE, trajectory, session_id="s1", steps=["tools.code_run → ok"])
    entries_after_remember = len(store.audit())
    effects_after_remember = len(_writes(tracker, _TRACE))

    loop.remember(_TRACE, trajectory, session_id="s1", steps=["tools.code_run → ok"])
    assert len(store.audit()) == entries_after_remember
    assert len(_writes(tracker, _TRACE)) == effects_after_remember

    compact_tracker = EffectTracker()
    compact_store = MemoryStore(
        effect_tracker=compact_tracker,
        summarizer=lambda _entries: "摘要：固定",  # noqa: ARG005 — 固定摘要用于制造同载荷
    )
    compact_store.write("L2", _entry(entry_id="e1", content="巡检 甲", session_id="s1"))
    compact_store.compact(session_id="s1")

    def summary_writes() -> list[Effect]:
        return [
            effect
            for effect in _writes(compact_tracker, "compaction.s1")
            if effect.target.startswith("compaction.summary.")
        ]

    assert len(summary_writes()) == 1

    # 恢复同一素材后重放同一会话压实 ⇒ 同 id 同载荷（含 from: 出处标签），不产生第二次摘要写入
    compact_store.write("L2", _entry(entry_id="e1", content="巡检 甲", session_id="s1"))
    compact_store.compact(session_id="s1")
    summaries = [
        entry for entry in compact_store.audit() if entry.id.startswith("compaction.summary.")
    ]
    assert len(summaries) == 1
    assert len(summary_writes()) == 1
