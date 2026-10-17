"""任务编排数据模型（orchestration）。

任务状态 / 子任务 / 计划 / 校验结果 / 交接 / 子 Agent 画像 等数据结构，
供 StateMachine / SubtaskDecomposer / MultiAgentRouter / TaskScheduler 消费。

对应接口：doc/03-interfaces/orchestration-interface.md §1 / §2 / §3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, cast

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


# 难易度三档（change 0123；词表来源：doc/openspec/specs/orchestration/spec.md
# 「难易度感知的调度策略」）。集合外取值**归一**为 `medium` 而非抛错 —— 难易度是模型自报的
# **弱信号**，其非法值不该让整次拆解失败（对齐 planner._parse 既有的「非法项剔除 /
# priority 非整数取 0」口径）；**配置键**取值非法则由 configuration 校验期阻断
# （信号来源不同的两者口径有意不同）。
DIFFICULTY_LEVELS: frozenset[str] = frozenset({"easy", "medium", "hard"})
DEFAULT_DIFFICULTY = "medium"


def normalize_difficulty(value: Any) -> str:
    """难易度归一：合法三档取自身（去空白 + 小写），否则回落 ``medium``。"""
    level = str(value or "").strip().lower()
    return level if level in DIFFICULTY_LEVELS else DEFAULT_DIFFICULTY


@dataclass
class Subtask:
    """分步子任务：目标 + 验收标准 + 依赖 DAG + 优先级 + 难易度。"""

    id: str
    goal: str
    acceptance: str
    depends_on: list[str] = field(default_factory=list[str])
    priority: int = 0
    difficulty: str = DEFAULT_DIFFICULTY  # 三档 easy/medium/hard（change 0123；调度策略的输入）

    def __post_init__(self) -> None:
        # 构造即归一（含 plan_from_dict 反序列化与检查点重建路径）⇒ 不变量单点收口
        self.difficulty = normalize_difficulty(self.difficulty)


@dataclass
class Plan:
    """拆解产物：子任务集 + 拓扑序 + 波次划分 + 顶层目标与成功标准。"""

    subtasks: list[Subtask]
    goal: str
    order: list[str] = field(default_factory=list[str])
    success_criteria: list[str] = field(default_factory=list[str])
    waves: list[list[str]] = field(default_factory=list[list[str]])
    replans: int = 0  # 已用重新拆解次数（随检查点持久化；change 0246）


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
    session_id: str = ""  # 会话 ID（转交子 loop，使子 Agent 轨迹按自身会话归组；缺省空串）


@dataclass
class AgentProfile:
    """子 Agent 画像：唯一 id + 能力标签（路由匹配依据）+ 可编排执行单元。"""

    agent_id: str
    capabilities: list[str] = field(default_factory=list[str])
    loop: LoopPlugin | None = None


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    """Plan → 可检查点持久化 dict（断点续跑重建用）。"""
    return {
        "goal": plan.goal,
        "subtasks": [
            {
                "id": s.id,
                "goal": s.goal,
                "acceptance": s.acceptance,
                "depends_on": list(s.depends_on),
                "priority": s.priority,
                "difficulty": s.difficulty,
            }
            for s in plan.subtasks
        ],
        "order": list(plan.order),
        "success_criteria": list(plan.success_criteria),
        "waves": [list(wave) for wave in plan.waves],
        "replans": plan.replans,
    }


def plan_from_dict(data: dict[str, Any]) -> Plan:
    """dict → Plan（检查点重建）；缺字段按空值兜底，不抛裸异常。"""
    items = [
        cast(dict[str, Any], item) for item in data.get("subtasks", []) if isinstance(item, dict)
    ]
    subtasks = [
        Subtask(
            id=str(item.get("id", "")),
            goal=str(item.get("goal", "")),
            acceptance=str(item.get("acceptance", "")),
            depends_on=[str(dep) for dep in item.get("depends_on", [])],
            priority=int(item.get("priority", 0)),
            # 旧检查点缺该键 ⇒ 回落 medium（`__post_init__` 同口径归一）
            difficulty=str(item.get("difficulty", DEFAULT_DIFFICULTY)),
        )
        for item in items
    ]
    return Plan(
        subtasks=subtasks,
        goal=str(data.get("goal", "")),
        order=[str(sid) for sid in data.get("order", [])],
        success_criteria=[str(c) for c in data.get("success_criteria", [])],
        waves=[[str(sid) for sid in wave] for wave in data.get("waves", [])],
        # 旧检查点缺该键 ⇒ 0（不保留恢复预算，行为与引入前一致）
        replans=int(data.get("replans", 0)),
    )
