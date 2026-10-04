"""崩溃恢复端到端（change 0062 / 账本 E12）。

既有 ``tests/test_durability.py`` 覆盖的是**内存 store 模拟**的幂等续跑；本文件补两件
规格「崩溃恢复」承诺、而此前**无处验证**的事：

① **写入原子性**（场景「持久化写入原子性」）：持久化写入中途被中断（半写）SHALL NOT
   损坏既有检查点集合 —— 旧实现 ``Path.write_text``（先截断再整写）会**整体丢失**；
② **真实进程崩溃后续跑**（场景「真实进程崩溃后续跑」）：子进程建检查点后被 ``SIGKILL``，
   另一进程重载存储 → 最近有效检查点可读 → 按**调用方游标**幂等续跑，副作用不重复。
"""

from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import sys

import pytest

from core.durability import CheckpointManager, CheckpointStore, CrashRecovery

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src"

# 子进程脚本：建 cp1 → 落一次"副作用" → 建 cp2（游标前进）→ SIGKILL 自杀。
# 游标语义即规格要求的分工：快照里的 cursor = 已应用的副作用数。
_CHILD = """
import os, signal, sys
from pathlib import Path

from core.durability import CheckpointManager, CheckpointStore

state_dir, effects_path = Path(sys.argv[1]), Path(sys.argv[2])
manager = CheckpointManager(CheckpointStore(state_dir / "checkpoints.jsonl"))
manager.create_checkpoint("task1", "sess1", {"cursor": 0})
with effects_path.open("a", encoding="utf-8") as fh:  # 副作用先落地
    fh.write("effect\\n")
manager.create_checkpoint("task1", "sess1", {"cursor": 1})  # 游标前进=已完成该步
os.kill(os.getpid(), signal.SIGKILL)  # 崩溃：无清理、无 flush 机会
"""

_TOTAL_EFFECTS = 1  # 本用例的任务只含一步副作用
_CHECKPOINTS_BEFORE_CRASH = 2  # 子进程崩溃前建的检查点数（cp1 + cp2）


# ---- ① 写入原子性（半写不损坏既有检查点） ----


def test_interrupted_persist_keeps_existing_checkpoints(tmp_path, monkeypatch) -> None:
    """写入中断（写到一半）→ 重载后既有检查点完好。

    以「先截断写目标再抛 OSError」模拟进程在写入中途被终止（真实 SIGKILL 落在哪一微秒
    不可控，故此处是**确定性的性质测试**）：失败点若在真文件上，既有检查点即整体丢失。
    """
    path = tmp_path / "checkpoints.jsonl"
    manager = CheckpointManager(CheckpointStore(path))
    first = manager.create_checkpoint("task1", "sess1", {"cursor": 1})
    assert path.exists() and path.read_text(encoding="utf-8").strip()

    def _half_write(self: pathlib.Path, *_args: object, **_kwargs: object) -> int:
        self.open("w").close()  # 截断（半写已落盘的部分）
        raise OSError("进程在写入中途被终止")

    monkeypatch.setattr(pathlib.Path, "write_text", _half_write)
    with pytest.raises(OSError):
        manager.create_checkpoint("task1", "sess1", {"cursor": 2})

    reloaded = CheckpointStore(path)
    assert [c.checkpoint_id for c in reloaded.list_checkpoints()] == [first.checkpoint_id]
    assert reloaded.get_snapshot(first.checkpoint_id).state == {"cursor": 1}


# ---- ② 真实进程 SIGKILL 后续跑 ----


def _crash_once(state_dir: pathlib.Path, effects: pathlib.Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(_SRC)}
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, str(state_dir), str(effects)],
        env=env,
        check=False,
    )
    assert proc.returncode == -signal.SIGKILL  # 确系被信号杀死，非正常退出


def test_real_sigkill_then_restore_and_resume(tmp_path) -> None:
    """真进程被杀 → 存储可重载、最近有效检查点可取、按游标续跑不重复副作用。"""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    effects = tmp_path / "effects.txt"
    _crash_once(state_dir, effects)

    # 崩溃后的"另一进程"：重载存储 —— 已持久化结果不丢失
    store = CheckpointStore(state_dir / "checkpoints.jsonl")
    assert len(store.list_checkpoints()) == _CHECKPOINTS_BEFORE_CRASH  # 写入已完成才崩，故都在
    recovery = CrashRecovery(store)
    handle = recovery.restore("task1")
    snapshot = store.get_snapshot(handle.checkpoint_id)
    assert snapshot is not None and snapshot.state == {"cursor": 1}  # 最近有效 = cp2
    assert handle.degraded is False

    def replay() -> None:
        """按检查点游标续跑：只补 cursor 之后的步骤（规格分工：跨进程幂等由游标保证）。"""
        applied = int(store.get_snapshot(handle.checkpoint_id).state["cursor"])  # type: ignore[union-attr]
        for _ in range(applied, _TOTAL_EFFECTS):
            with effects.open("a", encoding="utf-8") as fh:
                fh.write("effect\n")

    lines = lambda: len(effects.read_text(encoding="utf-8").splitlines())  # noqa: E731
    assert lines() == 1  # 崩溃前已落一次

    recovery.resume(handle, replay=replay)
    assert lines() == 1  # 游标说该步已完成 → 不重复产生副作用
    recovery.resume(handle, replay=replay)
    assert lines() == 1  # 同句柄幂等（第二个场景「恢复幂等性」）
