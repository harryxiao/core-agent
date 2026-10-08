"""常驻（pinned）笔记预算：显式优先级次序 + 整篇纳入 + 超限可见（change 0154／路线图 G1）。

对应规格：doc/openspec/specs/notes/spec.md「常驻（pinned）笔记（任务级硬约束锚）」
接口设计：doc/03-interfaces/notes-interface.md
"""

from __future__ import annotations

import warnings

import pytest

from core.notes import NoteEntry, NoteStore, parse_note, render_note
from core.notes.store import _MAX_PINNED_CHARS


def _section(note: NoteEntry) -> str:
    """与 ``pinned_digest`` 同口径的整篇渲染（供「片段是否在场」断言）。"""
    return f"## {note.title or note.note_id}（{note.note_id}）\n{note.content.strip()}"


def _pin(store: NoteStore, note_id: str, content: str, *, priority: int = 0) -> NoteEntry:
    store.update(NoteEntry(note_id=note_id, title=note_id, content=content))
    return store.set_pinned(note_id, pinned=True, priority=priority)


# ---- models：pin_priority 渲染 / 解析 ----


def test_render_parse_pin_priority_roundtrip() -> None:
    text = render_note(
        NoteEntry(note_id="c", title="约束", content="正文", pinned=True, pin_priority=5)
    )
    assert "- pin_priority: 5" in text
    assert parse_note(text, note_id="c").pin_priority == 5  # noqa: PLR2004 — 断言往返同一值


def test_render_omits_pin_priority_at_zero() -> None:
    """缺省 0 ⇒ 不输出该行（既有 canonical 渲染逐字不变）。"""
    text = render_note(NoteEntry(note_id="c", title="约束", content="正文"))
    assert "pin_priority" not in text


def test_parse_pin_priority_unparseable_is_zero() -> None:
    """fail-closed：手写成非整数 ⇒ 0（绝不意外抬高优先级）。"""
    text = "# 约束\n\n- id: c\n- pin_priority: abc\n\n## Notes\n\n正文\n"
    assert parse_note(text, note_id="c").pin_priority == 0


def test_render_parse_roundtrip_without_priority_is_byte_stable() -> None:
    """无优先级时渲染 ↔ 解析仍互为逆（零回归护栏）。"""
    note = NoteEntry(
        note_id="c",
        title="约束",
        content="正文",
        pinned=True,
        tags=["t"],
        search_queries=["约束", "t"],
    )
    assert parse_note(render_note(note), note_id="c") == note


# ---- store：优先级次序 ----


def test_pinned_orders_by_priority_desc_then_note_id(tmp_path) -> None:
    store = NoteStore(path=tmp_path)
    _pin(store, "c", "c-body", priority=5)
    _pin(store, "a", "a-body", priority=5)
    _pin(store, "b", "b-body", priority=1)

    assert [n.note_id for n in store.pinned()] == ["a", "c", "b"], (
        "优先级降序、同优先级 note_id 升序"
    )


# ---- store：整篇纳入，绝不半篇 ----


def test_digest_includes_whole_notes_and_excludes_overflow_whole(tmp_path) -> None:
    """超预算篇**整篇**排除（其任何片段都不在场），其后各篇不越过它挤入（前缀）。"""
    store = NoteStore(path=tmp_path)
    _pin(store, "a", "x" * 100)
    _pin(store, "b", "y" * 4000)  # 整篇纳入即超预算
    _pin(store, "c", "z" * 10)  # 次序在 b 之后 ⇒ 同样不入场

    with pytest.warns(RuntimeWarning):
        block = store.pinned_digest()

    assert "x" * 100 in block, "整篇 A 在场"
    assert "y" not in block, "B 一篇都不在场（绝不半篇）"
    assert "z" not in block, "B 之后的 C 不越过它挤入"
    assert store.pinned_overflow() == ["b", "c"]


def test_digest_without_overflow_neither_warns_nor_reports(tmp_path) -> None:
    store = NoteStore(path=tmp_path)
    _pin(store, "a", "x" * 100)

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # 任何告警都判失败
        block = store.pinned_digest()

    assert "x" * 100 in block
    assert store.pinned_overflow() == []


def test_digest_single_oversized_note_is_included_whole(tmp_path) -> None:
    """唯一（或次序首篇）的常驻笔记自身超限 ⇒ 仍整篇在场，块不为空；且留痕。"""
    store = NoteStore(path=tmp_path)
    _pin(store, "huge", "x" * (_MAX_PINNED_CHARS + 500))

    with pytest.warns(RuntimeWarning):
        block = store.pinned_digest()

    assert "x" * (_MAX_PINNED_CHARS + 500) in block, "整篇在场（块不空）"
    assert store.pinned_overflow() == [], "首篇在场，不在未进场之列"


def test_digest_empty_body_notes_neither_occupy_nor_overflow(tmp_path) -> None:
    """空正文常驻笔记：既不占块，也不计未进场。"""
    store = NoteStore(path=tmp_path)
    _pin(store, "blank", "   ")
    _pin(store, "real", "正文")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        block = store.pinned_digest()

    assert block == _section(store.get("real"))
    assert store.pinned_overflow() == []


# ---- store：set_pinned 的 priority ----


def test_set_pinned_priority_roundtrip_and_idempotent(tmp_path) -> None:
    store = NoteStore(path=tmp_path, clock=lambda: 100.0)
    store.update(NoteEntry(note_id="c", title="约束", content="正文"))

    store.set_pinned("c", pinned=True, priority=5)
    raw = (tmp_path / "c.md").read_text(encoding="utf-8")
    assert "- pin_priority: 5" in raw
    assert NoteStore(path=tmp_path).get("c").pin_priority == 5, "新实例读回（落盘真源）"  # noqa: PLR2004

    # 幂等：同一 (pinned, priority) 再置 ⇒ 不写盘、不 bump updated_at
    store2 = NoteStore(path=tmp_path, clock=lambda: 999.0)
    again = store2.set_pinned("c", pinned=True, priority=5)
    assert again.updated_at == 100.0, "同值重置不搅动时间戳"  # noqa: PLR2004 — 仍是首次时钟值
    assert (tmp_path / "c.md").read_text(encoding="utf-8") == raw


def test_unpin_zeroes_priority(tmp_path) -> None:
    store = NoteStore(path=tmp_path)
    store.update(NoteEntry(note_id="c", title="约束", content="正文"))
    store.set_pinned("c", pinned=True, priority=5)

    store.set_pinned("c", pinned=False)
    note = store.get("c")
    assert note.pinned is False
    assert note.pin_priority == 0
    assert "pin_priority" not in (tmp_path / "c.md").read_text(encoding="utf-8")


def test_observe_turn_preserves_pin_priority(tmp_path) -> None:
    """逐轮写回不得抹除常驻优先级（与既有保留 pinned 同口径）。"""
    store = NoteStore(path=tmp_path)
    store.update(
        NoteEntry(note_id="部署流程", title="部署流程", content="旧步骤", source="notes.turn")
    )
    store.set_pinned("部署流程", pinned=True, priority=7)

    steps = [
        "tools.code_run（script=pytest） → 全绿",
        "tools.code_run（script=deploy） → 上线",
    ]
    assert store.observe_turn("部署流程", steps, ok=True) is not None
    note = store.get("部署流程")
    assert "上线" in note.content, "同来源 ⇒ 覆盖式写回同一主题"
    assert note.pinned is True
    assert note.pin_priority == 7, "逐轮写回保留优先级"  # noqa: PLR2004 — 置位时给的优先级
