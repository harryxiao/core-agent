"""存量笔记清理：按来源移入回收目录（change 0295）。

**不物理删除**：先按原字节写进 ``<trash-dir>/<UTC stamp>/<note_id>.md``（0600），
再删 canonical，最后原子写 ``manifest.json``（0600）记录来源/时间/清单。
恢复 = 把回收目录里的 ``.md`` 复制回 notes 目录（canonical 文件名即 ``<note_id>.md``）。

对应规格：doc/openspec/specs/notes/spec.md（存量清理）
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ._private import write_private_json, write_private_text
from .store import NoteStore


@dataclass
class PruneResult:
    """一次清理的结果（``dry_run`` 时 ``trash_path``/``manifest_path`` 为 ``None``）。"""

    moved: list[str] = field(default_factory=list[str])
    kept_pinned: list[str] = field(default_factory=list[str])
    trash_path: Path | None = None
    manifest_path: Path | None = None


def prune_notes(  # noqa: PLR0913 — 运维入口显式参数，缺省值均安全
    store: NoteStore,
    *,
    source: str,
    trash_dir: Path,
    dry_run: bool = False,
    include_pinned: bool = False,
    clock: Callable[[], float] | None = None,
) -> PruneResult:
    """把 ``source`` 匹配的 canonical 笔记移入回收目录；缺省跳过 pinned。"""
    now = (clock if clock is not None else time.time)()
    stamp = datetime.fromtimestamp(now, tz=UTC).strftime("%Y%m%dT%H%M%SZ")

    moved: list[str] = []
    kept_pinned: list[str] = []
    for note in store.list():
        if note.source != source:
            continue
        if note.pinned and not include_pinned:
            kept_pinned.append(note.note_id)
            continue
        moved.append(note.note_id)

    if not moved or dry_run:
        return PruneResult(moved=moved, kept_pinned=kept_pinned)

    target = Path(trash_dir) / stamp
    for note_id in moved:
        raw = store.raw(note_id)
        if raw is None:  # 列出后、读取前被并发删除 —— 跳过，不伪造空文件
            continue
        write_private_text(target / f"{note_id}.md", raw)
        store.remove(note_id)

    manifest_path = target / "manifest.json"
    write_private_json(
        manifest_path,
        {
            "source": source,
            "timestamp": datetime.fromtimestamp(now, tz=UTC).isoformat(),
            "moved": moved,
            "kept_pinned": kept_pinned,
        },
    )
    return PruneResult(
        moved=moved,
        kept_pinned=kept_pinned,
        trash_path=target,
        manifest_path=manifest_path,
    )
