"""技能封装数据模型（skills）。

定义原子技能 / A/B 结果 / 路由匹配三组数据，供 SkillLibrary / VersionManager /
SkillRouter 消费。

对应接口：doc/03-interfaces/skills-interface.md §1 / §3 / §4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 技能字段上界（change 0255 / ADR-0246）：技能库注册与 SOP 确定性发布门、evolution
# 技能内容校验**共用同一组口径**（单一定义，避免两处各写一套数值漂移）。
MAX_SKILL_ID_CHARS = 120
MAX_INSTRUCTIONS_CHARS = 4000
MAX_DESCRIPTION_CHARS = 400
MAX_TASK_TYPES = 16
MAX_TASK_TYPE_CHARS = 80
MAX_PRECONDITIONS = 8
MAX_PRECONDITION_CHARS = 200


@dataclass
class Skill:
    """原子技能：可复用能力包（schema + 前置条件 + 执行说明）。"""

    skill_id: str  # 全局唯一，如 "skills.data_analysis.summarize"
    description: str
    task_types: list[str] = field(default_factory=list[str])
    preconditions: list[str] = field(default_factory=list[str])
    param_schema: Any = field(default_factory=dict[str, Any])
    instructions: str = ""
    version: str = "v1"
    status: str = "draft"  # draft | active | gray | deprecated


@dataclass
class ABResult:
    """A/B 测试对比结果。"""

    winner: str | None
    metric_delta: dict[str, float]  # 各指标对比（{"a": x, "b": y}）
    decision: str  # promote | revert | keep


@dataclass
class SkillMatch:
    """路由匹配结果：技能 + 匹配度。"""

    skill: Skill
    score: float  # 匹配度（语义 + 历史成功率 + 适用声明）
