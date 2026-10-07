"""半自动提升（semi-auto promotion）单测：摘要**首次越过**滚动上界 ⇒ 交付提升钩子一次。

对应规格：doc/openspec/specs/memory/spec.md「记忆压实」（上界可见性 + 提升钩子条款）、
doc/openspec/specs/notes/spec.md「会话摘要提升（promotion）」（半自动路径）。
change 0153 / ADR-0145 / 记忆三面路线图 G3。
"""

from __future__ import annotations

import warnings

from core.memory import MAX_SUMMARY_CHARS, MemoryEntry, MemoryStore
from core.notes import NoteStore, promote_session_summary

_LONG = "结论：" + "长" * (MAX_SUMMARY_CHARS + 100)  # 越过滚动上界的摘要
_SHORT = "结论：短"  # 未越界


def _episodic(entry_id: str, session_id: str, content: str = "事件") -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=["loop"],
        source="loop",
        session_id=session_id,
        kind="episodic",
        trace_id="t",
    )


class _Spy:
    """记录提升钩子调用（会话 id + 摘要条目）的替身。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, MemoryEntry]] = []

    def __call__(self, session_id: str, entry: MemoryEntry) -> object:
        self.calls.append((session_id, entry))
        return None


def test_summary_crossing_bound_delivers_promotion_once() -> None:
    """首次越界 ⇒ 钩子**恰一次**（收到 `(session_id, 该摘要条目)`）；已越界 ⇒ 不再交付。"""
    spy = _Spy()
    store = MemoryStore(summarizer=lambda entries: _LONG, summary_promoter=spy)
    store.write("L2", _episodic("e0", "s1"))

    store.compact(session_id="s1")

    assert [sid for sid, _ in spy.calls] == ["s1"], "越界 ⇒ 交付一次"
    assert spy.calls[0][1].content == _LONG, "交付的是本次产出的摘要条目"

    store.write("L2", _episodic("e1", "s1"))  # 既有摘要已越界
    store.compact(session_id="s1")

    assert len(spy.calls) == 1, "越界一次 ⇒ 交付恰一次，不重复"


def test_summary_below_bound_never_delivers() -> None:
    """摘要未越界 ⇒ 钩子从不被调用（边界护栏）。"""
    spy = _Spy()
    store = MemoryStore(summarizer=lambda entries: _SHORT, summary_promoter=spy)
    store.write("L2", _episodic("e0", "s1"))

    store.compact(session_id="s1")

    assert spy.calls == []


def test_promoter_unwired_is_noop() -> None:
    """未注入钩子（缺省）⇒ 不交付、摘要照写（零回归）。"""
    store = MemoryStore(summarizer=lambda entries: _LONG)
    store.write("L2", _episodic("e0", "s1"))

    store.compact(session_id="s1")

    assert store.summary_for("s1") is not None


def test_promoter_exception_degrades_without_aborting_compaction() -> None:
    """钩子抛错 ⇒ 降级（`warnings.warn` 留痕）+ 摘要照写 + 原条目照迁 L4。"""

    def boom(session_id: str, entry: MemoryEntry) -> object:
        raise RuntimeError("promoter boom")  # noqa: TRY003 — 测试用哨兵异常

    store = MemoryStore(summarizer=lambda entries: _LONG, summary_promoter=boom)
    store.write("L2", _episodic("e0", "s1"))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        store.compact(session_id="s1")

    assert any(issubclass(w.category, RuntimeWarning) for w in caught), "降级留痕"
    assert store.summary_for("s1") is not None, "摘要仍写回"
    archived = next(e for e in store.audit() if e.id == "e0")
    assert archived.layer == "L4", "原条目仍迁 L4（压实不中断）"


def test_empty_session_id_not_delivered() -> None:
    """`session_id` 为空串 ⇒ 不交付（摘要照写，key 归 `default`）。"""
    spy = _Spy()
    store = MemoryStore(summarizer=lambda entries: _LONG, summary_promoter=spy)
    store.write("L2", _episodic("e0", ""))

    store.compact()

    assert spy.calls == []
    assert store.summary_for("") is not None


def test_end_to_end_semi_auto_promotion_lands_canonical_not_pinned(tmp_path) -> None:
    """端到端：越界 ⇒ canonical 落一篇（`source=notes.promote`、`pinned=False`），且幂等单条。"""
    notes = NoteStore(path=tmp_path / "notes")

    def _promote(session_id: str, summary: MemoryEntry) -> object:
        return promote_session_summary(notes, summary, session_id=session_id, pin=False)

    store = MemoryStore(summarizer=lambda entries: _LONG, summary_promoter=_promote)
    store.write("L2", _episodic("e0", "s1"))

    store.compact(session_id="s1")

    assert len(list((tmp_path / "notes").glob("session-*.md"))) == 1, "越界 ⇒ canonical 落一篇"
    note = notes.get("session-s1")
    assert note.source == "notes.promote"
    assert note.pinned is False, "半自动 ⇒ **不**自动置常驻"
    assert "结论" in note.content

    store.write("L2", _episodic("e1", "s1"))  # 已越界
    store.compact(session_id="s1")

    assert len(list((tmp_path / "notes").glob("session-*.md"))) == 1, "幂等：仍单条"
    assert notes.get("session-s1").pinned is False
