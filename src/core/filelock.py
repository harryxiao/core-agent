"""跨进程文件锁（中性基础设施）：POSIX `flock` / Windows `msvcrt.locking`。

自 `core/orchestration/state_files.py` 抽出（change 0301）：记忆落盘（L2）与编排状态文件
（L3.5）都需要同一份平台锁实现，放在中性模块里让二者依赖同一单点真源、不反向依赖编排层。

两种锁语义：

- `exclusive_file_lock`：**fail-open** 的短建议锁 —— 取不到就无锁执行，绝不阻断调用方
  （后台登记 / 工作树 sidecar / 记忆落盘）。
- `try_exclusive_file_lock`：**fail-closed** 的非阻塞互斥锁 —— 取不到必须跳过共享资源
  （续跑批次单实例），绝不降级为无锁执行。

锁文件为同目录 `.<name>.lock`、模式 `0600`，释放时**不删除**（删除会让并发进程可能锁到
不同 inode）；进程退出（含崩溃）由 OS 释放。
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

LockOutcome = Literal["acquired", "busy", "unavailable"]


def _lock_fd(fd: int) -> bool:
    """对已打开的锁文件取独占锁；失败返回 `False`（调用方降级为无锁写）。"""
    try:
        if sys.platform == "win32":
            import msvcrt  # noqa: PLC0415 — 平台专属模块

            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl  # noqa: PLC0415 — 平台专属模块

            fcntl.flock(fd, fcntl.LOCK_EX)
    except OSError:
        return False
    return True


def _try_lock_fd(fd: int) -> bool:
    """非阻塞取独占锁；争用或失败返回 `False`（调用方 fail-closed）。"""
    try:
        if sys.platform == "win32":
            import msvcrt  # noqa: PLC0415 — 平台专属模块

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # noqa: PLC0415 — 平台专属模块

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock_fd(fd: int) -> None:
    """释放独占锁（失败忽略：进程退出时 OS 也会释放）。"""
    if sys.platform == "win32":
        import msvcrt  # noqa: PLC0415 — 平台专属模块

        with contextlib.suppress(OSError):
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl  # noqa: PLC0415 — 平台专属模块

        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def exclusive_file_lock(path: Path) -> Generator[None, None, None]:
    """短独占建议锁：取锁失败降级为无锁执行，绝不阻断调用方。"""
    lock_path = path.with_name(f".{path.name}.lock")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        yield
        return
    locked = _lock_fd(fd)
    try:
        yield
    finally:
        if locked:
            _unlock_fd(fd)
        os.close(fd)


@contextmanager
def try_exclusive_file_lock(path: Path) -> Generator[LockOutcome, None, None]:
    """非阻塞独占建议锁：fail-closed，取不到锁时调用方必须跳过共享资源。

    三态区分「正常争用」（`busy`，重叠调用是常态）与「锁不可用」（`unavailable`，
    权限/磁盘故障，运维需要告警）。
    """
    lock_path = path.with_name(f".{path.name}.lock")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        yield "unavailable"
        return
    locked = _try_lock_fd(fd)
    try:
        yield "acquired" if locked else "busy"
    finally:
        if locked:
            _unlock_fd(fd)
        os.close(fd)
