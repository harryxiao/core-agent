"""记忆运行指标与运维统计（change 0311 / SDD §11.1）。

- ``MemoryMetrics``：**实例作用域**的进程内累计计数（不落盘、不跨实例共享）；
- ``MemoryStats`` / ``collect_stats``：从**既有持久数据**（条目 + 治理审计行 + 文件体积）
  派生的只读聚合，供 `memory stats` 使用（零写回、零强化）。

对应规格：doc/openspec/specs/memory/spec.md「记忆运行指标快照」「记忆运维统计」。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .protocol import MemoryEntry

_WRITES_PREFIX = "memory.writes."
_FORGOTTEN_TAG = "forgotten"
_UNKNOWN = "unknown"
_KIND_SANITIZE = re.compile(r"[^a-z0-9_]")

# 固定键：未发生时也须出现在快照中（值为 0）。`memory.writes.<kind>` 动态出现，不在此列。
FIXED_METRIC_KEYS: tuple[str, ...] = (
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
    "memory.conflicts",
)


def metric_kind(kind: str) -> str:
    """`kind` → 指标键片段：小写化、非 ``[a-z0-9_]`` 替换为 ``_``、空值记 ``unknown``。"""
    slug = _KIND_SANITIZE.sub("_", kind.strip().lower())
    return slug or _UNKNOWN


def writes_metric(kind: str) -> str:
    """写入计数的指标键：``memory.writes.<kind>``。"""
    return f"{_WRITES_PREFIX}{metric_kind(kind)}"


class MemoryMetrics:
    """进程内累计计数（实例作用域；``snapshot()`` 为零 I/O、零效应的拷贝）。"""

    def __init__(self) -> None:
        self._values: dict[str, float] = {}

    def increment(self, name: str, value: float = 1.0) -> None:
        self._values[name] = self._values.get(name, 0.0) + value

    def snapshot(self) -> dict[str, float]:
        """固定键始终在场（未发生 ⇒ 0）；动态写入键按实际发生出现。"""
        out = {name: 0.0 for name in FIXED_METRIC_KEYS}
        out.update(self._values)
        return out


@dataclass(frozen=True)
class MemoryStats:
    """运维统计快照（只读聚合；映射字段按 key 排序输出）。"""

    storage_bytes: int = 0
    entries_total: int = 0
    entries_active: int = 0
    entries_retracted: int = 0
    entries_superseded: int = 0
    entries_forgotten: int = 0
    conflicts: int = 0
    content_bytes: int = 0
    by_layer: dict[str, int] = field(default_factory=dict[str, int])
    by_status: dict[str, int] = field(default_factory=dict[str, int])
    writes_by_kind: dict[str, int] = field(default_factory=dict[str, int])
    deletes_by_reason: dict[str, int] = field(default_factory=dict[str, int])
    forgets_by_reason: dict[str, int] = field(default_factory=dict[str, int])
    exports: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "storage_bytes": self.storage_bytes,
            "entries_total": self.entries_total,
            "entries_active": self.entries_active,
            "entries_retracted": self.entries_retracted,
            "entries_superseded": self.entries_superseded,
            "entries_forgotten": self.entries_forgotten,
            "conflicts": self.conflicts,
            "content_bytes": self.content_bytes,
            "by_layer": dict(sorted(self.by_layer.items())),
            "by_status": dict(sorted(self.by_status.items())),
            "writes_by_kind": dict(sorted(self.writes_by_kind.items())),
            "deletes_by_reason": dict(sorted(self.deletes_by_reason.items())),
            "forgets_by_reason": dict(sorted(self.forgets_by_reason.items())),
            "exports": self.exports,
        }


def collect_stats(
    entries: Iterable[MemoryEntry],
    audit_rows: Iterable[Mapping[str, Any]],
    *,
    storage_bytes: int = 0,
) -> MemoryStats:
    """聚合条目面 + 审计面（纯函数；不改动入参）。

    条目面：总数与各状态计数；``by_layer`` 只统计 active（层分布是「活记忆」视图）；
    ``content_bytes`` 只计 active 正文的 UTF-8 字节。``entries_forgotten`` 按 ``forgotten``
    标签计（与状态正交：墓碑亦可能已遗忘）。``conflicts`` 按 ``superseded_by`` 非空计
    （change 0312：与当前状态正交，墓碑化的旧版仍是一次历史冲突）。审计面按 ``op`` 与
    ``reason`` 派生。
    """
    by_layer, by_status, content_bytes, forgotten, conflicts = _count_entries(entries)

    writes_by_kind, deletes_by_reason, forgets_by_reason, exports = _count_audit(audit_rows)
    return MemoryStats(
        storage_bytes=storage_bytes,
        entries_total=sum(by_status.values()),
        entries_active=by_status.get("active", 0),
        entries_retracted=by_status.get("retracted", 0),
        entries_superseded=by_status.get("superseded", 0),
        entries_forgotten=forgotten,
        conflicts=conflicts,
        content_bytes=content_bytes,
        by_layer=by_layer,
        by_status=by_status,
        writes_by_kind=writes_by_kind,
        deletes_by_reason=deletes_by_reason,
        forgets_by_reason=forgets_by_reason,
        exports=exports,
    )


def _count_entries(
    entries: Iterable[MemoryEntry],
) -> tuple[dict[str, int], dict[str, int], int, int, int]:
    """条目面：层/状态计数、active 正文字节、`forgotten` 标签、冲突数。"""
    by_layer: dict[str, int] = {}
    by_status: dict[str, int] = {}
    content_bytes = 0
    forgotten = 0
    conflicts = 0
    for entry in entries:
        by_status[entry.status] = by_status.get(entry.status, 0) + 1
        if entry.status == "active":
            by_layer[entry.layer] = by_layer.get(entry.layer, 0) + 1
            content_bytes += len(entry.content.encode("utf-8"))
        if _FORGOTTEN_TAG in entry.tags:
            forgotten += 1
        if entry.superseded_by:
            conflicts += 1
    return by_layer, by_status, content_bytes, forgotten, conflicts


def _count_audit(
    audit_rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, int], dict[str, int], dict[str, int], int]:
    """审计行按 ``op`` 派生：写入 kind / 删除原因 / 遗忘原因 / 导出次数。"""
    buckets: dict[str, dict[str, int]] = {"write": {}, "delete": {}, "forget": {}}
    exports = 0
    for row in audit_rows:
        op = str(row.get("op") or "")
        bucket = buckets.get(op)
        if bucket is not None:
            key = "kind" if op == "write" else "reason"
            value = str(row.get(key) or "") or _UNKNOWN
            bucket[value] = bucket.get(value, 0) + 1
        if op == "export":
            exports += 1
    return buckets["write"], buckets["delete"], buckets["forget"], exports
