"""状态文件助手（orchestration）：短独占建议锁 + 原子 JSON 写。

从 `background.py` 抽出（change 0284），供后台登记与工作树 sidecar 共用：
POSIX `flock` / Windows `msvcrt.locking`，文件 `0600`，临时文件 + `fsync` + `os.replace`。
取锁失败降级为无锁写入（尽力而为，绝不阻断任务）。
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


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
    """短独占建议锁：取锁失败降级为无锁写入，绝不阻断任务。"""
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


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """同目录临时文件 + fsync + 原子替换（OSError 由调用方处理）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
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
