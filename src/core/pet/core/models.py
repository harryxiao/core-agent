"""宠物模式数据模型（pet-core）。

会话状态（四态）/ 任务类型（两类）/ 任务 三类数据结构。

对应接口：doc/03-interfaces/pet-mode-interface.md §1 / §2
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PetSessionState(Enum):
    """宠物会话状态（仅四态；让行复用 orchestration SUSPENDED 语义）。"""

    IDLE = "idle"  # 未激活
    ACTIVE = "active"  # 激活运行中
    BACKOFF = "backoff"  # 异常退避（故障隔离）
    TERMINATED = "terminated"  # 已终止


class PetTaskKind(Enum):
    """宠物任务类型（两类：信息收集 / 闲逛探索）。"""

    INFORMATION_GATHERING = "information_gathering"
    IDLE_EXPLORATION = "idle_exploration"


@dataclass
class PetTask:
    """宠物可分配任务：类型 + 目标 + 固定低优先级。"""

    kind: PetTaskKind
    goal: str
    priority: int = 0
