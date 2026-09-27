"""任务编排数据模型（orchestration）。

任务状态 / 子任务 / 计划 / 校验结果 / 交接 / 子 Agent 画像 等数据结构，
供 StateMachine / SubtaskDecomposer / MultiAgentRouter / TaskScheduler 消费。

对应接口：doc/03-interfaces/orchestration-interface.md §1 / §2 / §3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.loop import LoopPlugin


class TaskState(StrEnum):
    """任务状态机状态（合法转移表见 state_machine.py）。"""

    CREATED = "created"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    SUSPENDED = "suspended"
    RECOVERING = "recovering"
    FAILED = "failed"
    DONE = "done"


@dataclass
class Subtask:
    """分步子任务：目标 + 验收标准 + 依赖 DAG + 优先级。"""

    id: str
    goal: str
    acceptance: str
    depends_on: list[str] = field(default_factory=list[str])
    priority: int = 0


@dataclass
class Plan:
    """拆解产物：子任务集 + 拓扑序 + 波次划分 + 顶层目标与成功标准。"""

    subtasks: list[Subtask]
    goal: str
    order: list[str] = field(default_factory=list[str])
    success_criteria: list[str] = field(default_factory=list[str])
    waves: list[list[str]] = field(default_factory=list[list[str]])


@dataclass
class VerifyResult:
    """子任务校验结果：通过与否 + 原因。"""

    passed: bool
    reason: str


@dataclass
class TaskHandoff:
    """多 Agent 交接任务：任务描述 + 上下文包 + 验收标准 + 截止 + 优先级。"""

    task: str
    context_pack: dict[str, Any] = field(default_factory=dict[str, Any])
    acceptance: str = ""
    deadline: float | None = None
    priority: int = 0


@dataclass
class AgentProfile:
    """子 Agent 画像：唯一 id + 能力标签（路由匹配依据）+ 可编排执行单元。"""

    agent_id: str
    capabilities: list[str] = field(default_factory=list[str])
    loop: LoopPlugin | None = None
