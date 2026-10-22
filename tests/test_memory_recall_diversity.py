"""召回多样性（近重复 / 同会话上限）与注入统计单测。

对应规格：doc/openspec/specs/memory/spec.md「召回的多样性控制与注入统计」。
change 0304 / ADR-0294 / 台账 E240（memory-sdd P1-4 可落地子集）。
"""

from __future__ import annotations

from core.memory import MemoryEntry, MemoryStore


def _entry(
    entry_id: str,
    content: str,
    *,
    session_id: str = "",
    importance: float = 0.0,
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=[],
        source="loop",
        trace_id="t",
        session_id=session_id,
        importance=importance,
    )


def _store(*entries: MemoryEntry) -> MemoryStore:
    store = MemoryStore()
    for entry in entries:
        store.write("L2", entry)
    return store


def test_same_session_is_capped_at_three() -> None:
    """同会话最多 3 条（按排名取前 3），其他会话不受影响。"""
    store = _store(
        _entry("s1-a", "巡检 计划 A", session_id="s1", importance=0.9),
        _entry("s1-b", "巡检 计划 B", session_id="s1", importance=0.8),
        _entry("s1-c", "巡检 计划 C", session_id="s1", importance=0.7),
        _entry("s1-d", "巡检 计划 D", session_id="s1", importance=0.6),
        _entry("s2-a", "巡检 计划 E", session_id="s2", importance=0.5),
    )

    result = store.recall("巡检", budget=4096)

    ids = [entry.id for entry in result.entries]
    assert [entry_id for entry_id in ids if entry_id.startswith("s1-")] == [
        "s1-a",
        "s1-b",
        "s1-c",
    ]
    assert "s2-a" in ids
    assert result.excluded_by_diversity == 1


def test_scoped_session_recall_is_not_session_capped() -> None:
    """调用方已按 session_id 收窄 ⇒ 不再施加会话上限（否则截断该会话自身事实面）。"""
    store = _store(
        _entry("s1-a", "巡检 计划 A", session_id="s1", importance=0.9),
        _entry("s1-b", "巡检 计划 B", session_id="s1", importance=0.8),
        _entry("s1-c", "巡检 计划 C", session_id="s1", importance=0.7),
        _entry("s1-d", "巡检 计划 D", session_id="s1", importance=0.6),
        _entry("s2-a", "巡检 计划 E", session_id="s2", importance=0.5),
    )

    result = store.recall("巡检", budget=4096, session_id="s1")

    assert [entry.id for entry in result.entries] == ["s1-a", "s1-b", "s1-c", "s1-d"]
    assert result.excluded_by_diversity == 0


def test_global_entries_are_not_session_capped() -> None:
    """session_id="" 的全局条目不受每会话 3 条限制。"""
    store = _store(
        *[_entry(f"g{i}", f"巡检 全局 {i}", importance=1.0 - i * 0.05) for i in range(5)]
    )

    result = store.recall("巡检", budget=4096)

    assert [entry.id for entry in result.entries] == [f"g{i}" for i in range(5)]
    assert result.excluded_by_diversity == 0


def test_near_duplicate_keeps_best_ranked_only() -> None:
    """完全同文（含仅首尾空白差异）只留排名最高一条。"""
    store = _store(
        _entry("dup-high", "巡检 重复内容", importance=0.9),
        _entry("dup-low", "  巡检 重复内容  ", importance=0.5),
        _entry("unique", "巡检 独有内容", importance=0.8),
    )

    result = store.recall("巡检", budget=4096)

    assert [entry.id for entry in result.entries] == ["dup-high", "unique"]
    assert result.excluded_by_diversity == 1


def test_diversity_exclusions_do_not_consume_budget() -> None:
    """近重复在预算**之前**剔除：被剔条目不吃预算，后面的小条目仍可入选。

    正文成本（CJK 1 token/字符）：「巡检 」+100 汉字 = 102；「巡检 小」= 3。
    预算 204 恰容两条长正文 —— 若先按预算截断再抑制重复，dup-low 会占预算挤掉 unique。
    """
    long = "巡检 " + "甲" * 100
    store = _store(
        _entry("dup-high", long, importance=0.9),
        _entry("dup-low", long, importance=0.8),
        _entry("unique", "巡检 小", importance=0.0),
    )

    result = store.recall("巡检", budget=204)

    assert [entry.id for entry in result.entries] == ["dup-high", "unique"]
    assert result.excluded_by_diversity == 1
    assert result.excluded_by_budget == 0


def test_empty_content_is_not_deduplicated() -> None:
    """空正文不参与近重复抑制（否则所有空条目会被压成一条）。"""
    store = _store(
        _entry("empty-a", "", importance=0.1),
        _entry("empty-b", "   ", importance=0.2),
        _entry("filler", "巡检 有内容", importance=0.3),
    )

    result = store.recall("巡检", budget=4096)

    ids = {entry.id for entry in result.entries}
    assert {"empty-a", "empty-b", "filler"} <= ids


def test_stats_invariant_and_minimum_budget() -> None:
    """统计守恒；minimum_budget 恰好够再注入一条。"""
    store = _store(
        _entry("big-1", "巡检 " + "甲" * 20, importance=0.9),
        _entry("big-2", "巡检 " + "乙" * 20, importance=0.8),
        _entry("big-3", "巡检 " + "丙" * 20, importance=0.7),
    )

    result = store.recall("巡检", budget=10)

    assert result.injected_count == len(result.entries)
    assert result.matched_count == (
        result.injected_count + result.excluded_by_diversity + result.excluded_by_budget
    )
    assert result.excluded_by_budget == 2  # noqa: PLR2004 — 三条候选仅一条可容
    assert result.minimum_budget > 0

    wider = store.recall("巡检", budget=result.minimum_budget)
    assert wider.injected_count >= 2, "minimum_budget 应足够再注入一条"  # noqa: PLR2004


def test_read_delegates_to_recall_entries() -> None:
    """read() 与 recall().entries 返回同一集合与顺序。"""
    store = _store(
        _entry("r1", "巡检 一号", importance=0.9),
        _entry("r2", "巡检 二号", importance=0.5),
        _entry("r3", "巡检 三号", session_id="s1", importance=0.7),
    )

    recalled = store.recall("巡检", budget=4096)
    read_ids = [entry.id for entry in store.read("巡检", budget=4096)]
    assert read_ids == [entry.id for entry in recalled.entries]
