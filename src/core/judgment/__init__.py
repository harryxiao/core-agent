"""决策（judgment）：System One 决策小模型（JEV）+ 主 LLM 回退。

三原语统一入口（choice 选项路由 / score 评分筛选 / noul 布尔判断），
置信度低 / 端点不可达 / 超时自动回退主 LLM 兜底；每次决策产出
``DecisionTrace`` 落 observability 供进化/审批消费。

对应规格：doc/openspec/specs/judgment/spec.md
"""

from .compactor import Compactor
from .errors import JudgmentError, JudgmentErrorCode
from .guardrail import Guardrail
from .models import (
    DecisionPrimitive,
    DecisionRequest,
    DecisionResult,
    DecisionTrace,
)
from .provider import JEVProvider
from .router import DecisionRouter

__all__ = [
    "Compactor",
    "DecisionPrimitive",
    "DecisionRequest",
    "DecisionResult",
    "DecisionRouter",
    "DecisionTrace",
    "Guardrail",
    "JEVProvider",
    "JudgmentError",
    "JudgmentErrorCode",
]
