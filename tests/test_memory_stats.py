"""记忆运维统计的纯函数聚合（change 0311 / P2-5，规格「记忆运维统计」）。

聚合口径：条目面按 `status` / `layer` / `forgotten` 标签；审计面按 `op` 与 `reason`；
输出映射按 key 排序（稳定 JSON）。空输入 ⇒ 全 0。
"""

from __future__ import annotations

from typing import Any

from core.memory import MemoryEntry, collect_stats

_TS = 1_700_000_000.0
_STORAGE_BYTES = 1234


def _entry(  # noqa: PLR0913 — 测试工厂的显式字段
    entry_id: str,
    *,
    layer: str = "L2",
    status: str = "active",
    tags: list[str] | None = None,
    content: str = "内容",
    kind: str = "semantic",
) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer=layer,  # type: ignore[arg-type] — 测试内层字面量合法
        content=content,
        tags=tags or [],
        source="test",
        trace_id="t1",
        ts=_TS,
        session_id="s1",
        kind=kind,
        status=status,  # type: ignore[arg-type]
    )


def _audit(*rows: dict[str, Any]) -> list[dict[str, Any]]:
    return list(rows)


def test_entry_and_status_counts() -> None:
    entries = [
        _entry("a"),
        _entry("b", layer="L3"),
        _entry("c", layer="L4", status="retracted"),
        _entry("d", status="superseded"),
        _entry("e", layer="L4", tags=["forgotten"]),
    ]

    stats = collect_stats(entries, [], storage_bytes=_STORAGE_BYTES)

    assert stats.storage_bytes == _STORAGE_BYTES
    assert stats.entries_total == 5  # noqa: PLR2004 — 五条种子条目
    assert stats.entries_active == 3  # noqa: PLR2004 — 两条非 active
    assert stats.entries_retracted == 1
    assert stats.entries_superseded == 1
    assert stats.entries_forgotten == 1


def test_by_layer_counts_only_active() -> None:
    entries = [
        _entry("a", layer="L2"),
        _entry("b", layer="L2"),
        _entry("c", layer="L4", status="retracted"),
    ]

    stats = collect_stats(entries, [], storage_bytes=0)

    assert stats.by_layer == {"L2": 2}
    assert stats.by_status == {"active": 2, "retracted": 1}


def test_content_bytes_counts_active_only() -> None:
    entries = [
        _entry("a", content="abc"),
        _entry("b", content="中文"),
        _entry("c", content="墓碑", status="retracted"),
    ]

    stats = collect_stats(entries, [], storage_bytes=0)

    assert stats.content_bytes == len(b"abc") + len("中文".encode())


def test_audit_derived_counts() -> None:
    rows = _audit(
        {"op": "write", "kind": "episodic"},
        {"op": "write", "kind": "episodic"},
        {"op": "write", "kind": "semantic"},
        {"op": "delete", "reason": "tombstone"},
        {"op": "delete", "reason": "retention"},
        {"op": "delete", "reason": "retention"},
        {"op": "forget", "reason": "decay"},
        {"op": "export"},
        {"op": "export"},
    )

    stats = collect_stats([], rows, storage_bytes=0)

    assert stats.writes_by_kind == {"episodic": 2, "semantic": 1}
    assert stats.deletes_by_reason == {"retention": 2, "tombstone": 1}
    assert stats.forgets_by_reason == {"decay": 1}
    assert stats.exports == 2  # noqa: PLR2004 — 两条 export 行


def test_unknown_ops_ignored() -> None:
    stats = collect_stats([], _audit({"op": "recall"}, {"op": "write"}), storage_bytes=0)

    assert stats.writes_by_kind == {"unknown": 1}
    assert stats.deletes_by_reason == {}
    assert stats.forgets_by_reason == {}
    assert stats.exports == 0


def test_empty_inputs_are_all_zero() -> None:
    stats = collect_stats([], [], storage_bytes=0)

    assert stats.to_dict()["entries_total"] == 0
    assert stats.to_dict()["storage_bytes"] == 0
    assert stats.to_dict()["writes_by_kind"] == {}


def test_to_dict_maps_are_sorted() -> None:
    entries = [_entry("a", layer="L4"), _entry("b", layer="L2")]
    rows = _audit(
        {"op": "write", "kind": "semantic"},
        {"op": "write", "kind": "episodic"},
    )

    data = collect_stats(entries, rows, storage_bytes=0).to_dict()

    assert list(data["by_layer"]) == ["L2", "L4"]
    assert list(data["writes_by_kind"]) == ["episodic", "semantic"]


def test_stats_do_not_mutate_entries() -> None:
    entries = [_entry("a")]
    before = entries[0].content

    collect_stats(entries, [], storage_bytes=0)

    assert entries[0].content == before
