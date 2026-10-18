"""子进程执行 seam（tool-use，change 0259 / ADR-0249）。

L1 模块，仅依赖 stdlib：前景执行以**独立进程组**启动，超时 / 取消时终止整棵
进程树；后台执行以 ``Popen`` 写日志文件并登记到**有界**注册表。注册表元数据
原子落盘到 ``$CORE_STATE_DIR/processes.json``，进程重启后恢复为只读巡检项
（无 ``Popen`` 句柄，恢复项拒绝终止）。测试经 ``core.tools.execution`` 的
模块级 seam（``_create_subprocess_exec`` / ``_POPEN`` / ``_IS_WINDOWS`` /
``_save_registry``）替换，不 patch 全局 ``asyncio``。
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import json
import math
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, cast

# 可 monkeypatch 的平台常量：测试在非 Windows 宿主上也能验证 Windows 分支。
_IS_WINDOWS = sys.platform == "win32"
# Windows 专有常量在其它平台不存在 ⇒ 自带等值字面量（CREATE_NEW_PROCESS_GROUP）。
_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
_create_subprocess_exec = asyncio.create_subprocess_exec
_POPEN = subprocess.Popen
_REAP_TIMEOUT_S = 5.0
_MAX_JOBS = 32
_REGISTRY_VERSION = 1
_REGISTRY_NAME = "processes.json"
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
# /proc/<pid>/stat 去掉 pid 与 comm 后，starttime（字段 22）位于索引 19。
_STAT_STARTTIME_INDEX = 19


@dataclass(frozen=True)
class ExecResult:
    returncode: int
    stdout: str
    stderr: str


def _pid_alive(pid: int) -> bool:
    """进程存活探测。Windows 上 ``os.kill(pid, 0)`` 会终止进程，改用 OpenProcess。"""
    if _IS_WINDOWS:
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _windows_pid_alive(pid: int) -> bool:
    win_dll = getattr(ctypes, "WinDLL")  # noqa: B009 — WinDLL 仅在 Windows 定义
    kernel32: Any = win_dll("kernel32", use_last_error=True)
    handle: Any = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return bool(exit_code.value == _STILL_ACTIVE)
    finally:
        kernel32.CloseHandle(handle)


def _start_ticks(pid: int) -> int | None:
    """Linux 进程启动时刻（``/proc/<pid>/stat`` 字段 22）；其它平台返回 None。"""
    if not sys.platform.startswith("linux"):
        return None
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    fields = raw.rsplit(")", 1)[-1].split()
    if len(fields) <= _STAT_STARTTIME_INDEX:
        return None
    try:
        return int(fields[_STAT_STARTTIME_INDEX])
    except ValueError:
        return None


def _identity_ok(pid: int, expected: int | None) -> bool:
    """启动时刻不符 ⇒ PID 已被复用；无标识（非 Linux）只凭存活判定。"""
    if expected is None:
        return True
    return _start_ticks(pid) == expected


@dataclass(frozen=True)
class ManagedJob:
    """后台任务：本进程启动（``proc`` 为句柄）或跨重启恢复（``proc=None``）。

    **不**记录脚本正文 / 命令 / 环境变量，避免敏感内容驻留与落盘。
    """

    pid: int
    proc: Any | None
    output_path: Path
    started_at: float
    run_type: str
    start_ticks: int | None = None

    def is_running(self) -> bool:
        """存活判定：本进程任务看句柄；恢复项探测 pid 并核对启动时刻。"""
        if self.proc is not None:
            return self.proc.poll() is None
        if not _pid_alive(self.pid):
            return False
        return _identity_ok(self.pid, self.start_ticks)

    def info(self) -> dict[str, Any]:
        if self.proc is not None:
            returncode = self.proc.poll()
            running = returncode is None
        else:
            returncode = None
            running = self.is_running()
        return {
            "pid": self.pid,
            "run_type": self.run_type,
            "output_path": str(self.output_path),
            "started_at": self.started_at,
            "running": running,
            "returncode": returncode,
            "restored": self.proc is None,
        }


class ProcessRegistry:
    """后台任务注册表：有界、线程安全；元数据落盘并在重启后恢复。

    插入前淘汰已退出项；每次插入整体重写 ``processes.json``（原子替换）。
    落盘失败被吞掉（后台任务照常登记）；损坏文件按空注册表处理。
    """

    def __init__(self, max_jobs: int = _MAX_JOBS) -> None:
        self._max_jobs = max_jobs
        self._jobs: dict[int, ManagedJob] = {}
        self._lock = RLock()
        with contextlib.suppress(OSError):
            self._load()

    def add(self, job: ManagedJob) -> None:
        with self._lock:
            self._prune_locked()
            if len(self._jobs) >= self._max_jobs:
                raise RuntimeError(  # noqa: TRY003 — 结构化错误消息由 Provider 归一
                    f"后台任务已达上限 {self._max_jobs}，请先终止或等待退出"
                )
            self._jobs[job.pid] = job
            with contextlib.suppress(OSError):
                _save_registry(self._jobs)

    def get(self, pid: int) -> ManagedJob | None:
        with self._lock:
            return self._jobs.get(pid)

    def list(self) -> list[ManagedJob]:
        with self._lock:
            return [self._jobs[pid] for pid in sorted(self._jobs)]

    def _prune_locked(self) -> None:
        for pid in [pid for pid, job in self._jobs.items() if not job.is_running()]:
            del self._jobs[pid]

    def _load(self) -> None:
        path = _registry_path()
        if not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        record = cast("dict[str, Any]", payload)
        items = record.get("jobs")
        if not isinstance(items, list):
            return
        restored = [job for item in cast("list[object]", items) if (job := _restore_job(item))]

        restored.sort(key=lambda job: job.started_at)
        for job in restored[-self._max_jobs :]:
            self._jobs[job.pid] = job


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


def state_dir() -> Path:
    """全局状态目录：``$CORE_STATE_DIR``（缺省 ``~/.core/state``，0700）。"""
    base = Path(os.environ.get("CORE_STATE_DIR") or Path.home() / ".core" / "state")
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    with contextlib.suppress(OSError):
        os.chmod(base, 0o700)
    return base


def state_run_dir() -> Path:
    """后台输出目录：``$CORE_STATE_DIR``（缺省 ``~/.core/state``）/``run``（0700）。"""
    run_dir = state_dir() / "run"
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with contextlib.suppress(OSError):
        os.chmod(run_dir, 0o700)
    return run_dir


def _registry_path() -> Path:
    return state_dir() / _REGISTRY_NAME


def _job_record(job: ManagedJob) -> dict[str, Any]:
    """可持久化元数据：不含命令 / 脚本 / 环境变量。"""
    return {
        "pid": job.pid,
        "output_path": str(job.output_path),
        "started_at": job.started_at,
        "run_type": job.run_type,
        "start_ticks": job.start_ticks,
    }


def _restore_job(item: object) -> ManagedJob | None:  # noqa: PLR0911 — 逐字段校验多早退
    """校验并恢复一条登记项；非法条目返回 None（跳过，不抛错）。"""
    if not isinstance(item, dict):
        return None
    record = cast("dict[str, Any]", item)
    pid = record.get("pid")
    output_path = record.get("output_path")
    started_at = record.get("started_at")
    run_type = record.get("run_type")
    start_ticks = record.get("start_ticks")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if not isinstance(output_path, str) or not output_path:
        return None
    if not isinstance(started_at, (int, float)) or not math.isfinite(started_at):
        return None
    if not isinstance(run_type, str) or not run_type:
        return None
    if start_ticks is not None and (
        not isinstance(start_ticks, int) or isinstance(start_ticks, bool)
    ):
        return None
    return ManagedJob(
        pid=pid,
        proc=None,
        output_path=Path(output_path),
        started_at=float(started_at),
        run_type=run_type,
        start_ticks=start_ticks,
    )


def _save_registry(jobs: dict[int, ManagedJob]) -> None:
    """整体重写注册表文件：同目录临时文件 + fsync + 原子替换。"""
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {"version": _REGISTRY_VERSION, "jobs": [_job_record(job) for job in jobs.values()]}
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise


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
    pid = int(proc.pid)
    return ManagedJob(
        pid=pid,
        proc=proc,
        output_path=output_path,
        started_at=time.time(),
        run_type=run_type,
        start_ticks=_start_ticks(pid),
    )
