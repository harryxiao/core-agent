"""决策数据模型（judgment）。

决策原语三分类 + 统一请求/结果/轨迹：answers 按原语分形（noul→noul /
choice→choice+probabilities+confidence / score→score+legend+probabilities+confidence）。

对应接口：doc/03-interfaces/judgment-interface.md §1
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class DecisionPrimitive(StrEnum):
    """决策原语：choice 选项路由 / score 评分筛选 / noul 布尔判断。"""

    CHOICE = "choice"
    SCORE = "score"
    NOUL = "noul"


@dataclass
class DecisionRequest:
    """决策请求：state + 类型化问题，提交给 JEV System One 决策。"""

    primitive: DecisionPrimitive  # 决策原语
    state: str | dict[str, Any] | list[Any]  # 决策上下文状态
    questions: dict[str, Any]  # 类型化问题（map<question_id, Question>）
    options: list[str] | None = None  # choice 原语的候选选项
    threshold: float | None = None  # 置信度回退阈值（None 用默认）


@dataclass
class DecisionResult:
    """决策结果：answers 按原语分形。"""

    primitive: DecisionPrimitive
    answers: dict[str, Any]  # 类型化答案（map<question_id, Answer>）
    fallback: bool = False  # 是否回退主 LLM


@dataclass
class DecisionTrace:
    """决策轨迹：落 observability 供进化/审批消费。"""

    trace_id: str
    request: DecisionRequest
    result: DecisionResult
    ts: float  # 决策时间戳
