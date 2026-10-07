"""会话摘要提升（promotion）单测：`promote_session_summary`。

对应规格：doc/openspec/specs/notes/spec.md「会话摘要提升（promotion）」
change 0150 / ADR-0142 / 账本 E94。
"""

from __future__ import annotations

from core.memory import MemoryEntry
from core.notes import NoteStore, promote_session_summary


def _summary(session_id: str, content: str) -> MemoryEntry:
    """构造一条会话摘要条目（形态与 `_commit_summary` 落库一致）。"""
    key = session_id or "default"
    return MemoryEntry(
        id=f"compaction.summary.{key}",
        layer="L2",
        content=content,
        tags=["compaction", "summary"],
        source="compaction",
        trace_id=f"compaction.{key}",
        session_id=session_id,
        kind="semantic",
    )


def test_promote_writes_canonical_from_summary(tmp_path) -> None:
    store = NoteStore(path=tmp_path)

    summary = _summary("abc123", "结论：对外接口必须 HTTPS")
    note = promote_session_summary(store, summary, session_id="abc123")

    assert note is not None
    # 落盘真源：新实例读回
    reloaded = NoteStore(path=tmp_path).get(note.note_id)
    assert "对外接口必须 HTTPS" in reloaded.content
    assert reloaded.source == "notes.promote"
    assert reloaded.pinned is True, "提升即自动置常驻"


def test_promote_is_idempotent_single_note_per_session(tmp_path) -> None:
    store = NoteStore(path=tmp_path, clock=lambda: 10.0)

    first = promote_session_summary(store, _summary("s1", "第一次"), session_id="s1")
    assert first is not None
    store2 = NoteStore(path=tmp_path, clock=lambda: 20.0)
    second = promote_session_summary(store2, _summary("s1", "第二次"), session_id="s1")

    assert second is not None and second.note_id == first.note_id
    promoted = [n for n in NoteStore(path=tmp_path).list() if n.note_id.startswith("session-")]
    assert len(promoted) == 1, "同会话重复提升 ⇒ 单条，不增长"
    assert "第二次" in promoted[0].content, "覆盖式：内容为第二次"


def test_promote_note_id_derived_deterministically(tmp_path) -> None:
    store = NoteStore(path=tmp_path)

    a = promote_session_summary(store, _summary("sess-9", "x"), session_id="sess-9")
    b = promote_session_summary(store, _summary("sess-9", "y"), session_id="sess-9")

    assert a is not None and b is not None
    assert a.note_id == b.note_id == "session-sess-9"


def test_promote_as_overrides_note_id(tmp_path) -> None:
    store = NoteStore(path=tmp_path)

    note = promote_session_summary(
        store, _summary("s1", "x"), session_id="s1", as_note_id="my-topic", title="我的主题"
    )

    assert note is not None and note.note_id == "my-topic"
    assert NoteStore(path=tmp_path).get("my-topic").title == "我的主题"


def test_promote_tags_carry_session_provenance(tmp_path) -> None:
    store = NoteStore(path=tmp_path)

    note = promote_session_summary(store, _summary("s1", "x"), session_id="s1")

    assert note is not None
    assert "session:s1" in note.tags and "summary" in note.tags


def test_promote_empty_slug_returns_none_and_writes_nothing(tmp_path) -> None:
    store = NoteStore(path=tmp_path)

    result = promote_session_summary(store, _summary("...", "x"), session_id="...")

    assert result is None, "session_id 无可派生 slug 且未给显式 id ⇒ 不写盘"
    assert list(tmp_path.glob("*.md")) == [], "不产生任何 canonical 文件"
