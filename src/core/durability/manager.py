"""检查点管理 / 崩溃恢复 / 时间旅行（durability）。

- :class:`CheckpointManager`：显式创建检查点 + 快照寻址。
- :class:`CrashRecovery`：崩溃后自动恢复到最近有效检查点，损坏回退更早并
  标记 degraded，续跑幂等。
- :class:`TimeTravel`：恢复状态 + 复用 :class:`~core.plugin_registry.EffectTracker`
  撤销检查点之后的写类副作用。

对应接口：doc/03-interfaces/durability-interface.md §3 / §4 / §5
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any, cast

from core.plugin_registry import EffectTracker

from .errors import DurabilityError, DurabilityErrorCode
from .models import Checkpoint, RestoreHandle, Snapshot
from .store import CheckpointStore


class CheckpointManager:
    """检查点生命周期管理。"""

    def __init__(self, store: CheckpointStore) -> None:
        self._store = store

    def create_checkpoint(
        self,
        task_id: str,
        session_id: str,
        state: dict[str, Any],
        parent_id: str | None = None,
    ) -> Checkpoint:
        checkpoint = Checkpoint(
            checkpoint_id=uuid.uuid4().hex,
            ts=time.time(),
            task_id=task_id,
            session_id=session_id,
            parent_id=parent_id,
            pinned=False,
        )
        snapshot = Snapshot(
            snapshot_id=uuid.uuid4().hex,
            checkpoint_id=checkpoint.checkpoint_id,
            state=state,
            diff=None,
        )
        self._store.put(checkpoint, snapshot)
        return checkpoint

    def list_checkpoints(
        self,
        *,
        checkpoint_id: str | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
        ts_range: tuple[float, float] | None = None,
    ) -> list[Checkpoint]:
        result = self._store.list_checkpoints()
        if checkpoint_id is not None:
            result = [cp for cp in result if cp.checkpoint_id == checkpoint_id]
        if task_id is not None:
            result = [cp for cp in result if cp.task_id == task_id]
        if session_id is not None:
            result = [cp for cp in result if cp.session_id == session_id]
        if ts_range is not None:
            start, end = ts_range
            result = [cp for cp in result if start <= cp.ts <= end]
        return result

    def get_snapshot(self, checkpoint_id: str) -> Snapshot:
        checkpoint = self._store.get_checkpoint(checkpoint_id)
        if checkpoint is None:
            raise DurabilityError(
                DurabilityErrorCode.CHECKPOINT_NOT_FOUND, f"检查点不存在: {checkpoint_id}"
            )
        if self._store.is_corrupt(checkpoint_id):
            raise DurabilityError(
                DurabilityErrorCode.CHECKPOINT_CORRUPT, f"检查点损坏: {checkpoint_id}"
            )
        snapshot = self._store.get_snapshot(checkpoint_id)
        if snapshot is None:
            raise DurabilityError(
                DurabilityErrorCode.CHECKPOINT_CORRUPT, f"检查点快照缺失: {checkpoint_id}"
            )
        return snapshot


class CrashRecovery:
    """崩溃恢复：取最近有效检查点，损坏回退更早，续跑幂等。"""

    def __init__(self, store: CheckpointStore) -> None:
        self._store = store
        self._resumed: set[str] = set()

    def restore(self, task_id: str) -> RestoreHandle:
        checkpoints = sorted(
            [cp for cp in self._store.list_checkpoints() if cp.task_id == task_id],
            key=lambda cp: cp.ts,
            reverse=True,
        )
        degraded = False
        for checkpoint in checkpoints:
            snapshot = self._store.get_snapshot(checkpoint.checkpoint_id)
            if snapshot is None:
                degraded = True
                continue
            return RestoreHandle(
                handle_id=uuid.uuid4().hex,
                task_id=task_id,
                checkpoint_id=checkpoint.checkpoint_id,
                resume_cursor=checkpoint.checkpoint_id,
                degraded=degraded,
            )
        raise DurabilityError(
            DurabilityErrorCode.CHECKPOINT_NOT_FOUND, f"任务 {task_id} 无有效检查点"
        )

    def resume(self, handle: RestoreHandle, replay: Callable[[], None] | None = None) -> None:
        """幂等续跑：同一句柄只重放一次，不重复产生副作用。"""
        if handle.handle_id in self._resumed:
            return
        self._resumed.add(handle.handle_id)
        if replay is not None:
            replay()


class TimeTravel:
    """时间旅行：恢复到检查点状态 + 撤销检查点后的写类副作用。"""

    def __init__(self, store: CheckpointStore, effect_tracker: EffectTracker | None = None) -> None:
        self._store = store
        self._effect_tracker = effect_tracker

    def rollback(self, checkpoint_id: str) -> Snapshot:
        snapshot = self._store.get_snapshot(checkpoint_id)
        if snapshot is None:
            raise DurabilityError(
                DurabilityErrorCode.CHECKPOINT_NOT_FOUND, f"检查点不存在: {checkpoint_id}"
            )
        if self._effect_tracker is not None:
            trace_ids = cast(list[str], snapshot.state.get("trace_ids") or [])
            for trace_id in trace_ids:
                self._effect_tracker.rollback(trace_id)
        return snapshot
