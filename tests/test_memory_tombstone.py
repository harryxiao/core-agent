"""删除/保留期的墓碑化（change 0309 / ADR-0299）。

钉住：`retract` 清正文、置 `retracted`、迁 L4、保留 `content_hash`；墓碑退出检索 / 教训 /
压实材料，但审计与导出可见；可逆、跨进程持久；未知 id 零副作用。
"""

from __future__ import annotations

import time
from pathlib import Path

from core.memory import FileBackend, MemoryAuditLog, MemoryEntry, MemoryStore
from core.plugin_registry import EffectTracker


def _entry(entry_id: str, *, content: str = "正文", tags: list[str] | None = None) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=list(tags or []),
        source="loop",
        trace_id="t1",
        ts=time.time() - 86400.0,
        session_id="s1",
        kind="episodic",
    )


def _store(*, path: Path | None = None, audit: Path | None = None) -> MemoryStore:
    return MemoryStore(
        backend=FileBackend(path) if path is not None else FileBackend(),
        effect_tracker=EffectTracker(),
        audit_log=MemoryAuditLog(audit) if audit is not None else None,
    )


def _by_id(store: MemoryStore, entry_id: str) -> MemoryEntry:
    return next(entry for entry in store.audit(None) if entry.id == entry_id)


def test_retract_clears_body_and_marks_status(tmp_path: Path) -> None:
    store = _store(audit=tmp_path / "audit.jsonl")
    store.write("L2", _entry("e1", content="api key = sk-abcdefgh12345678"))
    original_hash = _by_id(store, "e1").content_hash

    assert store.retract("e1") is True

    entry = _by_id(store, "e1")
    assert (entry.layer, entry.status, entry.content) == ("L4", "retracted", "")
    assert entry.content_hash == original_hash
    assert "retracted" in entry.tags
    rows = MemoryAuditLog(tmp_path / "audit.jsonl").read(None)
    assert [(row["op"], row["reason"]) for row in rows][-1] == ("delete", "tombstone")


def test_retracted_entry_leaves_injection_surfaces() -> None:
    store = _store()
    store.write("L2", _entry("e1", content="需要忘记的内容", tags=["failure"]))

    assert store.retract("e1") is True

    assert store.read("需要忘记的内容") == []
    assert store.recall("需要忘记的内容").entries == []
    assert store.failure_lessons("s1") == []


def test_retract_unknown_id_is_noop(tmp_path: Path) -> None:
    store = _store(audit=tmp_path / "audit.jsonl")

    assert store.retract("missing") is False
    assert MemoryAuditLog(tmp_path / "audit.jsonl").read(None) == []


def test_tombstone_persists_across_reload(tmp_path: Path) -> None:
    path = tmp_path / "memory.jsonl"
    store = _store(path=path)
    store.write("L2", _entry("e1", content="原正文"))

    assert store.retract("e1") is True
    reloaded = MemoryStore(backend=FileBackend(path))

    entry = _by_id(reloaded, "e1")
    assert (entry.status, entry.content, entry.layer) == ("retracted", "", "L4")


def test_retract_is_reversible() -> None:
    tracker = EffectTracker()
    store = MemoryStore(backend=FileBackend(), effect_tracker=tracker)
    store.write("L2", _entry("e1", content="原正文"))

    assert store.retract("e1") is True
    report = tracker.rollback("retract.e1")

    assert report.undo_failed == []
    entry = _by_id(store, "e1")
    assert (entry.status, entry.content, entry.layer, "retracted" in entry.tags) == (
        "active",
        "原正文",
        "L2",
        False,
    )


def test_audit_and_export_surface_keep_tombstone() -> None:
    """墓碑是治理面记录：`audit()` 可见、导出快照含空正文与保留哈希。"""
    store = _store()
    store.write("L2", _entry("e1"))
    assert store.retract("e1") is True

    rows = store.audit(None)
    assert [entry.id for entry in rows] == ["e1"]
    assert rows[0].status == "retracted"
    assert rows[0].content == ""
    assert rows[0].content_hash


def test_tombstone_not_in_compaction_material() -> None:
    store = _store()
    store.write("L2", _entry("gone"))
    store.write("L2", _entry("keep"))
    assert store.retract("gone") is True

    groups = store._episodic_groups("s1")  # type: ignore[reportPrivateUsage]  # noqa: SLF001
    assert [entry.id for entry in groups["s1"]] == ["keep"]
