"""里程碑报告锚定单测（change 0273 / PA-08 方案 B）。

对应规格：doc/openspec/specs/notes/spec.md「里程碑报告锚定（milestone anchoring）」
"""

from __future__ import annotations

import pathlib

from core.memory import MemoryEntry
from core.notes import NoteEntry, NoteStore, close_milestone
from core.notes.milestone import (
    MAX_MILESTONE_CHARS,
    MILESTONE_PIN_PRIORITY,
    MILESTONE_SOURCE,
)


def _store(tmp_path: pathlib.Path) -> NoteStore:
    return NoteStore(path=tmp_path / "notes")


def _fact(entry_id: str, content: str, session_id: str = "s1") -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=["key_fact", f"session:{session_id}"],
        source="memory",
        session_id="",
        trace_id="t",
    )


def _summary(session_id: str, content: str) -> MemoryEntry:
    return MemoryEntry(
        id=f"compaction.summary.{session_id}",
        layer="L2",
        content=content,
        tags=["compaction", "summary"],
        source="compaction",
        session_id=session_id,
        trace_id="t",
    )


def test_milestone_writes_structured_pinned_note(tmp_path: pathlib.Path) -> None:
    """一键收口 ⇒ 固定节次序、置常驻、缺省高优先级。"""
    store = _store(tmp_path)
    note = close_milestone(
        store,
        milestone="M1 上线",
        conclusions=["接口联调通过"],
        decisions=["存储用 SQLite"],
        constraints=["对外接口必须 HTTPS"],
    )

    assert note is not None
    assert note.note_id == "milestone-m1-上线"
    assert note.source == MILESTONE_SOURCE
    assert note.pinned is True
    assert note.pin_priority == MILESTONE_PIN_PRIORITY

    content = note.content
    assert content.index("## 结论") < content.index("## 关键决策") < content.index("## 硬约束")
    assert "接口联调通过" in content
    assert "存储用 SQLite" in content
    assert "对外接口必须 HTTPS" in content
    assert [item.note_id for item in store.pinned()] == [note.note_id]


def test_milestone_idempotent_overwrite(tmp_path: pathlib.Path) -> None:
    """同一里程碑重复收口 ⇒ 单条覆盖、不增长。"""
    store = _store(tmp_path)
    close_milestone(store, milestone="m1", conclusions=["第一次结论"])
    close_milestone(store, milestone="m1", conclusions=["第二次结论"])

    notes = store.list()
    assert [note.note_id for note in notes] == ["milestone-m1"]
    assert "第二次结论" in notes[0].content
    assert "第一次结论" not in notes[0].content


def test_milestone_assembles_summary_and_keyfacts_deterministically(
    tmp_path: pathlib.Path,
) -> None:
    """会话摘要进结论节；keyfact 按 id 升序进关键事实节（确定性）。"""
    store = _store(tmp_path)
    facts = [
        _fact("keyfact.zeta", "zeta: 2"),
        _fact("keyfact.alpha", "alpha: 1"),
    ]
    note = close_milestone(
        store,
        milestone="m1",
        session_id="s1",
        summary=_summary("s1", "阶段一完成：接口联调通过"),
        key_facts=facts,
    )

    assert note is not None
    assert "阶段一完成：接口联调通过" in note.content
    assert "## 关键事实" in note.content
    assert note.content.index("- alpha: 1") < note.content.index("- zeta: 2")

    again = close_milestone(
        store,
        milestone="m1",
        session_id="s1",
        summary=_summary("s1", "阶段一完成：接口联调通过"),
        key_facts=list(reversed(facts)),
    )
    assert again is not None
    assert again.content == note.content


def test_milestone_empty_content_writes_nothing(tmp_path: pathlib.Path) -> None:
    """无显式条目、无摘要、无 keyfact ⇒ 不写盘。"""
    store = _store(tmp_path)
    assert close_milestone(store, milestone="m1") is None
    assert store.list() == []


def test_milestone_empty_slug_writes_nothing(tmp_path: pathlib.Path) -> None:
    """派生 id 为空且未给显式 id ⇒ 不写盘。"""
    store = _store(tmp_path)
    assert close_milestone(store, milestone="!!!", conclusions=["X"]) is None
    assert store.list() == []


def test_milestone_source_guard_and_explicit_override(tmp_path: pathlib.Path) -> None:
    """撞外来源且未给 --as ⇒ 拒绝且正文逐字不变；显式 --as ⇒ 授权覆写。"""
    store = _store(tmp_path)
    manual = NoteEntry(
        note_id="milestone-m1",
        title="人工主题",
        content="人工正文",
        source="notes",
        pinned=True,
    )
    store.update(manual)
    before = store.get("milestone-m1")

    assert close_milestone(store, milestone="m1", conclusions=["X"]) is None
    after = store.get("milestone-m1")
    assert after.title == before.title
    assert after.content == before.content
    assert after.updated_at == before.updated_at

    note = close_milestone(
        store,
        milestone="m1",
        conclusions=["X"],
        as_note_id="milestone-m1",
    )
    assert note is not None
    assert note.source == MILESTONE_SOURCE
    assert note.title == "人工主题", "未给 --title 时沿用既有标题"
    assert store.get("milestone-m1").title == "人工主题"


def test_milestone_redacts_and_bounds(tmp_path: pathlib.Path) -> None:
    """密钥形态先脱敏；正文有界且保留头部、截断可见。"""
    store = _store(tmp_path)
    secret = "sk-abcdefghijklmnop"
    long_tail = "尾" * (MAX_MILESTONE_CHARS + 500)
    note = close_milestone(
        store,
        milestone="m1",
        conclusions=[f"token {secret}", "头部结论"],
        constraints=[long_tail],
    )

    assert note is not None
    assert secret not in note.content
    assert "<redacted>" in note.content
    assert len(note.content) <= MAX_MILESTONE_CHARS
    assert "头部结论" in note.content
    assert "[truncated" in note.content


def test_milestone_priority_outranks_manual_pinned(tmp_path: pathlib.Path) -> None:
    """缺省优先级使里程碑先于普通常驻；--priority 0 ⇒ 按 note_id 排序。"""
    store = _store(tmp_path)
    store.update(NoteEntry(note_id="a-manual", content="人工约束", pinned=True))

    milestone = close_milestone(store, milestone="m1", conclusions=["X"])
    assert milestone is not None
    assert [note.note_id for note in store.pinned()] == ["milestone-m1", "a-manual"]

    close_milestone(store, milestone="m1", conclusions=["X"], priority=0)
    assert [note.note_id for note in store.pinned()] == ["a-manual", "milestone-m1"]
