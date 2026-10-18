"""durability 单元测试（对齐规格场景 + §7 专属校验锚点）。

覆盖：显式检查点寻址、崩溃恢复（最近/损坏回退/幂等续跑）、
时间旅行与副作用回滚协同、保留策略（数量/时间/配额/pin 保护）。
"""

from __future__ import annotations

import time
import warnings
from datetime import timedelta
from pathlib import Path

import pytest

from core.durability import (
    CheckpointManager,
    CheckpointStore,
    CrashRecovery,
    DurabilityError,
    DurabilityErrorCode,
    RetentionManager,
    RetentionPolicy,
    TimeTravel,
)
from core.plugin_registry import Effect, EffectTracker

_MAX_COUNT = 2  # 数量上限（RetentionPolicy.max_count 阈值）


def _manager() -> tuple[CheckpointStore, CheckpointManager]:
    store = CheckpointStore()
    return store, CheckpointManager(store)


# ---- 显式检查点 ----


def test_create_checkpoint_addressable() -> None:
    store, manager = _manager()
    checkpoint = manager.create_checkpoint("task1", "sess1", {"step": 1})
    snapshot = manager.get_snapshot(checkpoint.checkpoint_id)
    assert snapshot.state == {"step": 1}
    assert manager.list_checkpoints(task_id="task1") == [checkpoint]


def test_get_snapshot_missing_raises() -> None:
    store, manager = _manager()
    with pytest.raises(DurabilityError) as exc_info:
        manager.get_snapshot("nope")
    assert exc_info.value.code is DurabilityErrorCode.CHECKPOINT_NOT_FOUND


# ---- 崩溃恢复 ----


def test_restore_from_latest_checkpoint() -> None:
    store, manager = _manager()
    manager.create_checkpoint("task1", "sess1", {"step": 1})
    time.sleep(0.002)  # 保证时间戳单调递增
    manager.create_checkpoint("task1", "sess1", {"step": 2})
    recovery = CrashRecovery(store)
    handle = recovery.restore("task1")
    snapshot = store.get_snapshot(handle.checkpoint_id)
    assert snapshot is not None and snapshot.state == {"step": 2}
    assert handle.degraded is False


def test_resume_idempotent() -> None:
    store, manager = _manager()
    manager.create_checkpoint("task1", "sess1", {"step": 1})
    recovery = CrashRecovery(store)
    handle = recovery.restore("task1")
    replays: list[int] = []

    def replay() -> None:
        replays.append(1)

    recovery.resume(handle, replay=replay)
    recovery.resume(handle, replay=replay)
    assert replays == [1]


def test_restore_corrupt_falls_back() -> None:
    store, manager = _manager()
    first = manager.create_checkpoint("task1", "sess1", {"step": 1})
    time.sleep(0.002)
    second = manager.create_checkpoint("task1", "sess1", {"step": 2})
    store.corrupt(second.checkpoint_id)
    recovery = CrashRecovery(store)
    handle = recovery.restore("task1")
    assert handle.checkpoint_id == first.checkpoint_id
    assert handle.degraded is True


def test_restore_no_checkpoint_raises() -> None:
    store = CheckpointStore()
    recovery = CrashRecovery(store)
    with pytest.raises(DurabilityError) as exc_info:
        recovery.restore("task1")
    assert exc_info.value.code is DurabilityErrorCode.CHECKPOINT_NOT_FOUND


# ---- 时间旅行 ----


def test_time_travel_rolls_back_effects() -> None:
    store = CheckpointStore()
    manager = CheckpointManager(store)
    tracker = EffectTracker()
    undone: list[str] = []
    tracker.record(
        Effect(
            op="write",
            target="f.txt",
            undo=lambda: undone.append("f.txt"),
            reversible=True,
            coeffect=["filesystem:write"],
            trace_id="t1",
            ts=0.0,
        )
    )
    checkpoint = manager.create_checkpoint("task1", "sess1", {"trace_ids": ["t1"], "step": 1})
    time_travel = TimeTravel(store, effect_tracker=tracker)
    snapshot = time_travel.rollback(checkpoint.checkpoint_id)
    assert snapshot.state == {"trace_ids": ["t1"], "step": 1}
    assert undone == ["f.txt"]


def test_time_travel_missing_checkpoint_raises() -> None:
    """未知检查点 ⇒ ``CHECKPOINT_NOT_FOUND``（生产入口 `time-travel` 的失败面）。"""
    time_travel = TimeTravel(CheckpointStore(), effect_tracker=EffectTracker())
    with pytest.raises(DurabilityError) as exc_info:
        time_travel.rollback("ghost")
    assert exc_info.value.code is DurabilityErrorCode.CHECKPOINT_NOT_FOUND


# ---- 保留策略 ----


def test_retention_applies_max_count() -> None:
    store, manager = _manager()
    for step in range(5):
        manager.create_checkpoint("task1", "sess1", {"step": step})
    retention = RetentionManager(store)
    retention.apply(RetentionPolicy(max_count=_MAX_COUNT))
    assert len(store.list_checkpoints()) == _MAX_COUNT


def test_retention_time_window() -> None:
    store, manager = _manager()
    manager.create_checkpoint("task1", "sess1", {"step": 0})
    retention = RetentionManager(store)
    retention.apply(RetentionPolicy(time_window=timedelta(seconds=0)))
    assert store.list_checkpoints() == []


def test_retention_pin_protected() -> None:
    store, manager = _manager()
    oldest = manager.create_checkpoint("task1", "sess1", {"step": 0})
    for step in range(1, 4):
        manager.create_checkpoint("task1", "sess1", {"step": step})
    retention = RetentionManager(store)
    retention.pin(oldest.checkpoint_id)
    retention.apply(RetentionPolicy(max_count=1))
    assert oldest in store.list_checkpoints()


def test_retention_quota_exceeded() -> None:
    store, manager = _manager()
    checkpoint = manager.create_checkpoint("task1", "sess1", {"payload": "x" * 100})
    retention = RetentionManager(store)
    retention.pin(checkpoint.checkpoint_id)  # 全部 pinned，无法清理
    with pytest.raises(DurabilityError) as exc_info:
        retention.apply(RetentionPolicy(storage_quota=10))
    assert exc_info.value.code is DurabilityErrorCode.RETENTION_QUOTA_EXCEEDED


# ---- 加载损坏行（change 0264）----

_CANARY = "SECRET-CANARY-DO-NOT-ECHO"


def test_corrupt_lines_warn_once_and_keep_valid_checkpoints(tmp_path: Path) -> None:
    """坏 JSON + 结构不符行 ⇒ 一次告警（仅条数 + 文件名），合法行仍可读。"""
    path = tmp_path / "checkpoints.jsonl"
    manager = CheckpointManager(CheckpointStore(path))
    good = manager.create_checkpoint("task1", "sess1", {"step": 1})
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f'\n{{"broken": {_CANARY}\n')  # 坏 JSON（前置换行：_persist 不留尾换行）
        fh.write('{"checkpoint": {}, "snapshot": {}}\n')  # 合法 JSON、缺必需字段

    with pytest.warns(UserWarning) as caught:
        reloaded = CheckpointStore(path)

    assert [c.checkpoint_id for c in reloaded.list_checkpoints()] == [good.checkpoint_id]
    assert len(caught) == 1
    message = str(caught[0].message)
    assert "2" in message
    assert path.name in message
    assert _CANARY not in message


def test_clean_load_emits_no_warning(tmp_path: Path) -> None:
    path = tmp_path / "checkpoints.jsonl"
    manager = CheckpointManager(CheckpointStore(path))
    manager.create_checkpoint("task1", "sess1", {"step": 1})

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        CheckpointStore(path)

    assert not [w for w in caught if issubclass(w.category, UserWarning)]


# ---- 批量删除与一次性清理（change 0286）----


def test_delete_many_persists_once_and_ignores_missing(tmp_path: Path) -> None:
    path = tmp_path / "checkpoints.jsonl"
    manager = CheckpointManager(CheckpointStore(path))
    first = manager.create_checkpoint("task1", "sess1", {"step": 1})
    second = manager.create_checkpoint("task1", "sess1", {"step": 2})
    keep = manager.create_checkpoint("task2", "sess1", {"step": 3})

    assert CheckpointStore(path).delete_many([first.checkpoint_id, "missing"]) == 1

    reloaded = CheckpointStore(path)
    assert {cp.checkpoint_id for cp in reloaded.list_checkpoints()} == {
        second.checkpoint_id,
        keep.checkpoint_id,
    }


def test_retention_prune_is_batched_and_protects_pinned(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "checkpoints.jsonl")
    manager = CheckpointManager(store)
    oldest = manager.create_checkpoint("task1", "sess1", {"step": 1})
    middle = manager.create_checkpoint("task1", "sess1", {"step": 2})
    newest = manager.create_checkpoint("task1", "sess1", {"step": 3})
    store.set_pinned(oldest.checkpoint_id, True)

    pruned = RetentionManager(store).prune(RetentionPolicy(max_count=1))

    assert pruned == 1  # 只删未 pinned 的最旧一个；pinned 不计入上限
    assert {cp.checkpoint_id for cp in store.list_checkpoints()} == {
        oldest.checkpoint_id,
        newest.checkpoint_id,
    }
    assert middle.checkpoint_id not in {cp.checkpoint_id for cp in store.list_checkpoints()}
