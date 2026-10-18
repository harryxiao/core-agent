"""后台登记跨进程归属与写锁（change 0283 / ADR-0273）。

覆盖：

* **归属字段**：`owner_pid` / `owner_start` 落盘，模型快照不暴露。
* **存活判定**：存活 owner 的 running 保持 running（不误标中断、不可取消/重入队）；
  死 owner、旧格式、pid 复用 ⇒ interrupted。
* **合并写**：并发进程新增/更新的条目不被本进程陈旧快照覆盖或回滚；锁文件 0600。
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from core.loop import LoopResult
from core.orchestration import background
from core.orchestration.background import BackgroundAgentRegistry

_FILE_MODE = 0o600


class _OkLoop:
    async def arun(self, task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG002
        return LoopResult(reply=f"完成:{task}", trace_id="t-sub")


class _BlockingLoop:
    def __init__(self) -> None:
        self.gate = asyncio.Event()

    async def arun(self, task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG002
        await self.gate.wait()
        return LoopResult(reply="完成", trace_id="t-sub")


def _dead_pid() -> int:
    """一个确定已退出的 pid（子进程退出后不会被本测试复用）。"""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=30)
    return proc.pid


def _record(task_id: str, started_at: float, **extra: Any) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "agent_id": "coding",
        "task": f"任务 {task_id}",
        "status": "running",
        "started_at": started_at,
        "finished_at": None,
        "session_id": "s1",
        "error": "",
        **extra,
    }


def _write_state(path: Path, tasks: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps({"version": 1, "tasks": tasks}), encoding="utf-8")


# ── 1. 归属字段 ────────────────────────────────────────────────────────────


def test_owner_fields_persisted_but_not_exposed(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"

    async def scenario() -> str:
        registry = BackgroundAgentRegistry(state_path=path)
        task_id = registry.spawn(_OkLoop(), "写代码", agent_id="coding", session_id="s1")
        await registry.wait(task_id)
        assert "owner_pid" not in registry.get(task_id).info()  # type: ignore[union-attr]
        return task_id

    task_id = asyncio.run(scenario())
    raw = json.loads(path.read_text(encoding="utf-8"))
    entry = next(item for item in raw["tasks"] if item["task_id"] == task_id)
    assert entry["owner_pid"] == os.getpid()
    assert entry["owner_start"] == background._process_start_token(os.getpid())  # noqa: SLF001


def test_pid_liveness_helpers() -> None:
    assert background._pid_alive(os.getpid()) is True  # noqa: SLF001
    assert background._pid_alive(_dead_pid()) is False  # noqa: SLF001
    assert background._pid_alive(0) is False  # noqa: SLF001


# ── 2. 加载映射 ────────────────────────────────────────────────────────────


def test_live_owner_running_task_stays_running(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"

    async def scenario() -> None:
        registry = BackgroundAgentRegistry(state_path=path)
        loop = _BlockingLoop()
        task_id = registry.spawn(loop, "长任务", agent_id="coding", session_id="s1")

        other = BackgroundAgentRegistry(state_path=path)
        info = other.get(task_id)
        assert info is not None
        assert info.status == "running", "存活 owner 的在途任务不得被误标中断"
        assert info.finished_at is None
        assert "进程重启" not in info.error
        assert other.running_count() == 1
        assert other.cancel(task_id) is False, "本进程没有该任务的 asyncio.Task 句柄"
        assert other.drain_notices("s1") == []

        loop.gate.set()
        await registry.wait(task_id)

    asyncio.run(scenario())


def test_dead_owner_running_task_becomes_interrupted(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"
    _write_state(path, [_record("bg-dead", 1.0, owner_pid=_dead_pid(), owner_start="")])

    registry = BackgroundAgentRegistry(state_path=path)
    info = registry.get("bg-dead")
    assert info is not None
    assert info.status == "interrupted"
    assert info.finished_at is None
    assert "进程重启" in info.error
    assert registry.running_count() == 0


def test_legacy_record_without_owner_becomes_interrupted(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"
    _write_state(path, [_record("bg-legacy", 1.0)])

    registry = BackgroundAgentRegistry(state_path=path)
    info = registry.get("bg-legacy")
    assert info is not None
    assert info.status == "interrupted"
    assert "进程重启" in info.error


def test_pid_reuse_not_treated_as_live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "background-tasks.json"
    _write_state(
        path,
        [_record("bg-reused", 1.0, owner_pid=os.getpid(), owner_start="boot-a")],
    )
    # 同一 pid 的“当前”启动标识已变 ⇒ 记录属于上一轮生命周期。
    monkeypatch.setattr(background, "_process_start_token", lambda pid: "boot-b")

    registry = BackgroundAgentRegistry(state_path=path)
    info = registry.get("bg-reused")
    assert info is not None
    assert info.status == "interrupted"


# ── 3. 合并写与锁 ──────────────────────────────────────────────────────────


def test_save_preserves_entries_added_by_other_registry(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"

    async def run(registry: BackgroundAgentRegistry, text: str) -> str:
        task_id = registry.spawn(_OkLoop(), text, agent_id="coding", session_id="s1")
        await registry.wait(task_id)
        return task_id

    async def scenario() -> set[str]:
        first = BackgroundAgentRegistry(state_path=path)
        first_id = await run(first, "任务 A")
        # B 加载后，A 又新增一个任务（B 内存中没有它）。
        second = BackgroundAgentRegistry(state_path=path)
        third = BackgroundAgentRegistry(state_path=path)
        third_id = await run(third, "任务 C")
        # B 自己的写入不得覆盖掉 C。
        fourth_id = await run(second, "任务 D")
        return {first_id, third_id, fourth_id}

    expected = asyncio.run(scenario())
    raw = json.loads(path.read_text(encoding="utf-8"))
    ids = {item["task_id"] for item in raw["tasks"]}
    assert ids == expected, "三个进程/实例的登记都必须保留"


def test_save_does_not_rollback_newer_disk_status(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"

    async def scenario() -> str:
        owner = BackgroundAgentRegistry(state_path=path)
        loop = _BlockingLoop()
        task_id = owner.spawn(loop, "长任务", agent_id="coding", session_id="s1")

        # B 加载时看到 running（owner 存活）。
        other = BackgroundAgentRegistry(state_path=path)
        assert other.get(task_id).status == "running"  # type: ignore[union-attr]

        # A 落终态；B 的快照仍是 running。
        loop.gate.set()
        await owner.wait(task_id)
        assert owner.get(task_id).status == "done"  # type: ignore[union-attr]

        # B 写自己的任务：不得把磁盘上的 done 回滚成 running。
        other_id = other.spawn(_OkLoop(), "任务 B", agent_id="coding", session_id="s1")
        await other.wait(other_id)
        return task_id

    task_id = asyncio.run(scenario())
    restored = BackgroundAgentRegistry(state_path=path)
    statuses = {info.task_id: info.status for info in restored.list()}
    assert statuses[task_id] == "done"


def test_merge_resanitizes_foreign_disk_record(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"
    canary = "sk-abcdefghijklmnop"
    _write_state(
        path,
        [
            {
                **_record("bg-foreign", 1.0),
                "task": f"调 API {canary} 后报告",
                "status": "done",
                "finished_at": 2.0,
            }
        ],
    )

    async def scenario() -> None:
        registry = BackgroundAgentRegistry(state_path=path)
        task_id = registry.spawn(_OkLoop(), "任务 B", agent_id="coding")
        await registry.wait(task_id)

    asyncio.run(scenario())
    raw = path.read_text(encoding="utf-8")
    assert canary not in raw, "合并写回的磁盘记录也必须脱敏"
    assert "<redacted>" in raw


def test_lock_file_created_with_private_mode(tmp_path: Path) -> None:
    path = tmp_path / "background-tasks.json"

    async def scenario() -> None:
        registry = BackgroundAgentRegistry(state_path=path)
        task_id = registry.spawn(_OkLoop(), "写代码", agent_id="coding")
        await registry.wait(task_id)

    asyncio.run(scenario())
    lock_path = path.with_name(f".{path.name}.lock")
    assert lock_path.exists()
    assert stat.S_IMODE(lock_path.stat().st_mode) == _FILE_MODE
