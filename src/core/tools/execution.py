"""子进程执行 seam（tool-use，change 0259 / ADR-0249）。

L1 模块，仅依赖 stdlib：前景执行以**独立进程组**启动，超时 / 取消时终止整棵
进程树；后台执行以 ``Popen`` 写日志文件并登记到**有界**注册表。测试经
``core.tools.execution`` 的模块级 seam（``_create_subprocess_exec`` /
``_POPEN`` / ``_IS_WINDOWS``）替换，不 patch 全局 ``asyncio``。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

# 可 monkeypatch 的平台常量：测试在非 Windows 宿主上也能验证 Windows 分支。
_IS_WINDOWS = sys.platform == "win32"
# Windows 专有常量在其它平台不存在 ⇒ 自带等值字面量（CREATE_NEW_PROCESS_GROUP）。
_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
_create_subprocess_exec = asyncio.create_subprocess_exec
_POPEN = subprocess.Popen
_REAP_TIMEOUT_S = 5.0
_MAX_JOBS = 32


@dataclass(frozen=True)
class ExecResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ManagedJob:
    """本进程启动的后台任务（**不**记录脚本正文，避免敏感内容驻留）。"""

    pid: int
    proc: Any
    output_path: Path
    started_at: float
    run_type: str

    def info(self) -> dict[str, Any]:
        returncode = self.proc.poll()
        return {
            "pid": self.pid,
            "run_type": self.run_type,
            "output_path": str(self.output_path),
            "started_at": self.started_at,
            "running": returncode is None,
            "returncode": returncode,
        }


class ProcessRegistry:
    """后台任务注册表：有界、线程安全；插入前淘汰已退出项。"""

    def __init__(self, max_jobs: int = _MAX_JOBS) -> None:
        self._max_jobs = max_jobs
        self._jobs: dict[int, ManagedJob] = {}
        self._lock = RLock()

    def add(self, job: ManagedJob) -> None:
        with self._lock:
            self._prune_locked()
            if len(self._jobs) >= self._max_jobs:
                raise RuntimeError(  # noqa: TRY003 — 结构化错误消息由 Provider 归一
                    f"后台任务已达上限 {self._max_jobs}，请先终止或等待退出"
                )
            self._jobs[job.pid] = job

    def get(self, pid: int) -> ManagedJob | None:
        with self._lock:
            return self._jobs.get(pid)

    def list(self) -> list[ManagedJob]:
        with self._lock:
            return [self._jobs[pid] for pid in sorted(self._jobs)]

    def _prune_locked(self) -> None:
        for pid in [pid for pid, job in self._jobs.items() if job.proc.poll() is not None]:
            del self._jobs[pid]


async def run_foreground(
    cmd: list[str], *, timeout: float, cwd: str | None = None, env: dict[str, str] | None = None
) -> ExecResult:
    """异步前景执行：独立进程组；超时 / 取消时终止整棵进程树。"""
    kwargs: dict[str, Any] = {
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "cwd": cwd,
        "env": env,
    }
    if _IS_WINDOWS:
        kwargs["creationflags"] = _CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = await _create_subprocess_exec(*cmd, **kwargs)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (TimeoutError, asyncio.CancelledError):
        await _terminate_and_reap(proc)
        raise
    return ExecResult(
        returncode=int(proc.returncode or 0),
        stdout=(stdout or b"").decode("utf-8", errors="replace"),
        stderr=(stderr or b"").decode("utf-8", errors="replace"),
    )


async def _terminate_and_reap(proc: Any) -> None:
    """终止进程树并回收直接子进程；回收失败不遮蔽原始超时 / 取消。"""
    kill_process_tree(proc)
    with contextlib.suppress(TimeoutError, ProcessLookupError, OSError):
        await asyncio.wait_for(proc.wait(), timeout=_REAP_TIMEOUT_S)


def kill_process_tree(proc: Any) -> None:
    """终止 ``proc`` 及其后代：POSIX 按进程组，Windows 用 ``taskkill /T /F``。"""
    pid = proc.pid
    if pid is None:
        return
    if _IS_WINDOWS:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            _kill_direct(proc)
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        _kill_direct(proc)


def _kill_direct(proc: Any) -> None:
    with contextlib.suppress(ProcessLookupError, OSError):
        proc.kill()


def state_run_dir() -> Path:
    """后台输出目录：``$CORE_STATE_DIR``（缺省 ``~/.core/state``）/``run``（0700）。"""
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    run_dir = base / "run"
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with contextlib.suppress(OSError):
        os.chmod(run_dir, 0o700)
    return run_dir


def new_output_path(run_type: str) -> Path:
    return state_run_dir() / f"{run_type}-{uuid.uuid4().hex}.log"


def spawn_background(
    cmd: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    run_type: str = "python",
) -> ManagedJob:
    """后台启动：stdout / stderr 合并写入 0600 日志文件，立即返回句柄。"""
    output_path = new_output_path(run_type)
    fd = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    handle = os.fdopen(fd, "wb")
    kwargs: dict[str, Any] = {
        "stdout": handle,
        "stderr": subprocess.STDOUT,
        "cwd": cwd,
        "env": env,
    }
    if _IS_WINDOWS:
        kwargs["creationflags"] = _CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        proc = _POPEN(list(cmd), **kwargs)
    except BaseException:
        handle.close()
        output_path.unlink(missing_ok=True)
        raise
    finally:
        handle.close()
    return ManagedJob(
        pid=int(proc.pid),
        proc=proc,
        output_path=output_path,
        started_at=time.time(),
        run_type=run_type,
    )
