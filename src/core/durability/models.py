"""持久化数据模型（durability）。

检查点 / 快照 / 恢复句柄 / 保留策略四类数据结构。

对应接口：doc/03-interfaces/durability-interface.md §1
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any


@dataclass
class Checkpoint:
    """检查点元数据：寻址一个时刻的任务执行位置。"""

    checkpoint_id: str
    ts: float
    task_id: str
    session_id: str
    parent_id: str | None
    pinned: bool = False


@dataclass
class Snapshot:
    """快照：检查点对应时刻的内存状态（+ 相对父快照的差异）。"""

    snapshot_id: str
    checkpoint_id: str
    state: dict[str, Any]
    diff: dict[str, Any] | None = None


@dataclass
class RestoreHandle:
    """恢复句柄：崩溃恢复 / 续跑时的游标载体。"""

    handle_id: str
    checkpoint_id: str
    resume_cursor: str
    degraded: bool = False


@dataclass
class RetentionPolicy:
    """保留策略：数量上限 / 时间窗口 / 存储配额，策略组合生效。"""

    max_count: int | None = None
    time_window: timedelta | None = None
    storage_quota: int | None = None
    strategy: str = "time_window"
