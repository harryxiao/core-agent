"""检查点运维入口（change 0286 / ADR-0276 / 台账 E222）。

规格锚点：`orchestration`「检查点运维入口」。本文件锁五件事：

- `task --forget <id>` 只删除精确任务（含 pinned）并清除自动续跑退避；
- 未知任务非零退出，且不改动任何数据；
- `task --prune-checkpoints` 按上限/时间窗口只清理未 pinned，输出计数；
- 缺边界、非法边界与模式组合冲突均为用法错误；
- 续跑批次锁被占用时两个动词都 fail-closed，不修改任何检查点。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.durability import Checkpoint, CheckpointManager, CheckpointStore, Snapshot
from core.entry import main
from core.orchestration.auto_resume import AutoResumeState
from core.orchestration.state_files import try_exclusive_file_lock


def _put(  # noqa: PLR0913 — 测试种子参数显式列出更易读
    store: CheckpointStore,
    checkpoint_id: str,
    task_id: str,
    *,
    ts: float,
    pinned: bool = False,
    done: bool = False,
) -> Checkpoint:
    checkpoint = Checkpoint(
        checkpoint_id=checkpoint_id,
        ts=ts,
        task_id=task_id,
        session_id="sess",
        parent_id=None,
        pinned=pinned,
    )
    snapshot = Snapshot(
        snapshot_id=f"snap-{checkpoint_id}",
        checkpoint_id=checkpoint_id,
        state={"done": done},
    )
    store.put(checkpoint, snapshot)
    return checkpoint


def _seed(path: Path) -> CheckpointStore:
    store = CheckpointStore(path)
    _put(store, "t1-a", "t1", ts=100.0)
    _put(store, "t1-b", "t1", ts=200.0, pinned=True)
    _put(store, "t2-a", "t2", ts=150.0)
    return store


def _ids(path: Path) -> set[str]:
    return {cp.checkpoint_id for cp in CheckpointStore(path).list_checkpoints()}


def test_forget_removes_only_target_task_and_clears_backoff(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    path = tmp_path / "checkpoints.jsonl"
    _seed(path)
    AutoResumeState(tmp_path / "auto-resume.json").record_attempt("t1")
    AutoResumeState(tmp_path / "auto-resume.json").record_attempt("t2")

    assert main(["task", "--forget", "t1"]) == 0

    assert _ids(path) == {"t2-a"}
    state = AutoResumeState(tmp_path / "auto-resume.json")
    assert state.attempts("t1") == 0  # 退避记录已清
    assert state.attempts("t2") == 1  # 其他任务不受影响
    out = capsys.readouterr()
    assert "[checkpoints_forgotten] task=t1 deleted=2" in out.out


def test_forget_unknown_task_exits_nonzero_without_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    path = tmp_path / "checkpoints.jsonl"
    _seed(path)

    assert main(["task", "--forget", "ghost"]) == 1

    assert _ids(path) == {"t1-a", "t1-b", "t2-a"}
    assert "未找到任务 ghost 的检查点" in capsys.readouterr().err


def test_forget_refuses_while_resume_batch_lock_held(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    path = tmp_path / "checkpoints.jsonl"
    _seed(path)

    with try_exclusive_file_lock(tmp_path / "auto-resume.json") as outcome:
        assert outcome == "acquired"
        assert main(["task", "--forget", "t1"]) == 1

    assert _ids(path) == {"t1-a", "t1-b", "t2-a"}
    assert "[checkpoints_locked]" in capsys.readouterr().err


def test_prune_max_count_keeps_newest_unpinned_and_all_pinned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    path = tmp_path / "checkpoints.jsonl"
    store = CheckpointStore(path)
    _put(store, "u-old", "t1", ts=100.0)
    _put(store, "u-mid", "t1", ts=200.0)
    _put(store, "u-new", "t1", ts=300.0)
    _put(store, "pinned-old", "t2", ts=50.0, pinned=True)

    assert main(["task", "--prune-checkpoints", "--max-count", "1"]) == 0

    assert _ids(path) == {"u-new", "pinned-old"}
    out = capsys.readouterr().out
    assert "[checkpoints_pruned] deleted=2 kept=2 pinned=1" in out


def test_prune_time_window_keeps_pinned(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    path = tmp_path / "checkpoints.jsonl"
    store = CheckpointStore(path)
    now = time.time()
    _put(store, "stale", "t1", ts=now - 3600)
    _put(store, "fresh", "t1", ts=now)
    _put(store, "stale-pinned", "t2", ts=now - 3600, pinned=True)

    assert main(["task", "--prune-checkpoints", "--older-than-s", "60"]) == 0

    assert _ids(path) == {"fresh", "stale-pinned"}


def test_prune_requires_a_bound_and_rejects_invalid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    path = tmp_path / "checkpoints.jsonl"
    _seed(path)

    assert main(["task", "--prune-checkpoints"]) == 1
    assert main(["task", "--prune-checkpoints", "--max-count", "0"]) == 1
    assert main(["task", "--prune-checkpoints", "--older-than-s", "-1"]) == 1
    assert _ids(path) == {"t1-a", "t1-b", "t2-a"}
    assert "用法" in capsys.readouterr().err


def test_maintenance_modes_are_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    path = tmp_path / "checkpoints.jsonl"
    _seed(path)

    assert main(["task", "--forget", "t1", "--resume-all"]) == 1
    assert main(["task", "目标", "--prune-checkpoints", "--max-count", "1"]) == 1
    assert _ids(path) == {"t1-a", "t1-b", "t2-a"}
    assert "用法" in capsys.readouterr().err


def test_prune_refuses_while_resume_batch_lock_held(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    path = tmp_path / "checkpoints.jsonl"
    _seed(path)

    with try_exclusive_file_lock(tmp_path / "auto-resume.json") as outcome:
        assert outcome == "acquired"
        assert main(["task", "--prune-checkpoints", "--max-count", "1"]) == 1

    assert _ids(path) == {"t1-a", "t1-b", "t2-a"}
    assert "[checkpoints_locked]" in capsys.readouterr().err


def test_forget_only_removes_exact_task_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    path = tmp_path / "checkpoints.jsonl"
    store = CheckpointStore(path)
    _put(store, "t10", "t10", ts=100.0)
    _put(store, "t1", "t1", ts=101.0)

    assert main(["task", "--forget", "t1"]) == 0
    assert _ids(path) == {"t10"}


def test_forget_clears_pinned_and_keeps_turn_namespace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    path = tmp_path / "checkpoints.jsonl"
    store = CheckpointStore(path)
    manager = CheckpointManager(store)
    pinned = manager.create_checkpoint("t1", "sess", {"done": False})
    store.set_pinned(pinned.checkpoint_id, True)
    _put(store, "turn-1", "turn.abc", ts=100.0)

    assert main(["task", "--forget", "t1"]) == 0
    assert _ids(path) == {"turn-1"}
