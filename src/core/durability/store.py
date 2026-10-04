"""检查点存储（durability）。

内存 dict + 可选 JSONL 落盘（``path=None`` 纯内存，测试友好），带
``threading.RLock`` 保证并发安全，对齐 memory 的 FileBackend 风格。

对应接口：doc/03-interfaces/durability-interface.md §2
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict
from pathlib import Path

from .models import Checkpoint, Snapshot


class CheckpointStore:
    """检查点与快照的持久化存储。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._checkpoints: dict[str, Checkpoint] = {}
        self._snapshots: dict[str, Snapshot] = {}
        self._corrupt: set[str] = set()
        self._lock = threading.RLock()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                self._load()

    def put(self, checkpoint: Checkpoint, snapshot: Snapshot) -> None:
        with self._lock:
            self._checkpoints[checkpoint.checkpoint_id] = checkpoint
            self._snapshots[checkpoint.checkpoint_id] = snapshot
            self._corrupt.discard(checkpoint.checkpoint_id)
            self._persist()

    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        with self._lock:
            return self._checkpoints.get(checkpoint_id)

    def get_snapshot(self, checkpoint_id: str) -> Snapshot | None:
        with self._lock:
            if checkpoint_id in self._corrupt:
                return None
            return self._snapshots.get(checkpoint_id)

    def is_corrupt(self, checkpoint_id: str) -> bool:
        with self._lock:
            return checkpoint_id in self._corrupt

    def list_checkpoints(self) -> list[Checkpoint]:
        with self._lock:
            return list(self._checkpoints.values())

    def set_pinned(self, checkpoint_id: str, pinned: bool) -> None:
        with self._lock:
            checkpoint = self._checkpoints.get(checkpoint_id)
            if checkpoint is not None:
                checkpoint.pinned = pinned
                self._persist()

    def corrupt(self, checkpoint_id: str) -> None:
        """标记检查点为损坏（崩溃恢复时回退更早检查点）。"""
        with self._lock:
            self._corrupt.add(checkpoint_id)

    def delete(self, checkpoint_id: str) -> None:
        with self._lock:
            self._checkpoints.pop(checkpoint_id, None)
            self._snapshots.pop(checkpoint_id, None)
            self._corrupt.discard(checkpoint_id)
            self._persist()

    def _persist(self) -> None:
        """原子提交：写同目录临时文件后 ``os.replace`` 替换。

        写入中途被终止（进程崩溃 / 半写）时，读者看到的仍是**上一版完整文件**，
        既有检查点不会部分覆盖或整体丢失（规格 durability「崩溃恢复」）。
        """
        if self._path is None:
            return
        lines = [
            json.dumps(
                {
                    "checkpoint": asdict(self._checkpoints[cid]),
                    "snapshot": asdict(self._snapshots[cid]),
                    "corrupt": cid in self._corrupt,
                },
                ensure_ascii=False,
            )
            for cid in self._checkpoints
        ]
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        os.replace(tmp, self._path)

    def _load(self) -> None:
        if self._path is None:
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue  # 损坏行跳过（崩溃后重启容忍局部损坏）
            checkpoint = Checkpoint(**record["checkpoint"])
            snapshot = Snapshot(**record["snapshot"])
            self._checkpoints[checkpoint.checkpoint_id] = checkpoint
            self._snapshots[checkpoint.checkpoint_id] = snapshot
            if record.get("corrupt"):
                self._corrupt.add(checkpoint.checkpoint_id)
