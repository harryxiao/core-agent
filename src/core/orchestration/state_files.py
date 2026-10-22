"""状态文件助手（orchestration）：独占建议锁 + 原子 JSON 写。

从 `background.py` 抽出（change 0284），供后台登记与工作树 sidecar 共用。
锁实现已迁至中性模块 `core/filelock.py`（change 0301，与记忆落盘共用同一单点真源），
本模块 re-export 以保持既有调用方与测试零改动。

两种锁语义并存（change 0285）：

- `exclusive_file_lock`：**fail-open** 的短建议锁 —— 取不到就无锁写，绝不阻断任务
  （后台登记 / 工作树 sidecar 的尽力而为一致性）。
- `try_exclusive_file_lock`：**fail-closed** 的非阻塞互斥锁 —— 取不到必须跳过共享资源
  （续跑批次单实例），绝不降级为无锁执行。
"""

from __future__ import annotations

import contextlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from core.filelock import (
    LockOutcome,
    exclusive_file_lock,
    try_exclusive_file_lock,
)

__all__ = [
    "LockOutcome",
    "atomic_write_json",
    "exclusive_file_lock",
    "try_exclusive_file_lock",
]


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
