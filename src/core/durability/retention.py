"""检查点保留策略（durability）。

按数量上限 / 时间窗口 / 存储配额自动清理过期检查点，pinned 检查点受保护；
全部 pinned 仍超配额时抛 RETENTION_QUOTA_EXCEEDED。

对应接口：doc/03-interfaces/durability-interface.md §7
"""

from __future__ import annotations

import json
import time

from .errors import DurabilityError, DurabilityErrorCode
from .models import Checkpoint, RetentionPolicy
from .store import CheckpointStore


class RetentionManager:
    """检查点保留策略执行器。"""

    def __init__(self, store: CheckpointStore) -> None:
        self._store = store

    def prune(self, policy: RetentionPolicy) -> int:
        """按数量上限 / 时间窗口批量清理未 pinned 检查点，返回删除数（change 0286）。

        两个通道同时给出时取并集；pinned 检查点永不删除（其不计入 ``max_count``）。
        待删集合一次 ``CheckpointStore.delete_many`` 落盘，供一次性运维清理避免
        O(n²) 次全文件重写。
        """
        checkpoints = self._sorted()
        doomed: dict[str, None] = {}
        if policy.max_count is not None:
            unpinned = [cp for cp in checkpoints if not cp.pinned]
            excess = max(0, len(unpinned) - policy.max_count)
            for checkpoint in unpinned[:excess]:
                doomed[checkpoint.checkpoint_id] = None
        if policy.time_window is not None:
            cutoff = time.time() - policy.time_window.total_seconds()
            for checkpoint in checkpoints:
                if not checkpoint.pinned and checkpoint.ts < cutoff:
                    doomed[checkpoint.checkpoint_id] = None
        return self._store.delete_many(doomed)

    def apply(self, policy: RetentionPolicy) -> None:
        self.prune(policy)

        if policy.storage_quota is not None:
            all_checkpoints = self._sorted()
            total = sum(self._size(cp) for cp in all_checkpoints)
            unpinned = [cp for cp in all_checkpoints if not cp.pinned]
            while total > policy.storage_quota and unpinned:
                oldest = unpinned.pop(0)
                self._store.delete(oldest.checkpoint_id)
                total -= self._size(oldest)
            if total > policy.storage_quota:
                raise DurabilityError(
                    DurabilityErrorCode.RETENTION_QUOTA_EXCEEDED,
                    f"存储配额超限: {total} > {policy.storage_quota}",
                )

    def pin(self, checkpoint_id: str) -> None:
        self._store.set_pinned(checkpoint_id, True)

    def unpin(self, checkpoint_id: str) -> None:
        self._store.set_pinned(checkpoint_id, False)

    def _sorted(self) -> list[Checkpoint]:
        return sorted(self._store.list_checkpoints(), key=lambda cp: cp.ts)

    def _size(self, checkpoint: Checkpoint) -> int:
        snapshot = self._store.get_snapshot(checkpoint.checkpoint_id)
        if snapshot is None:
            return 0
        return len(json.dumps(snapshot.state, ensure_ascii=False, default=str))
