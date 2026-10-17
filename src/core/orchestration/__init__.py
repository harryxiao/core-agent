"""多 Agent 任务编排（orchestration，L4 编排层）。

任务状态机 + 子任务拆解 + 多 Agent 协同 + 并行扇出调度 + 断点续跑，
向下依赖 loop / tools / llm-provider / durability / context / plugin-registry，
反向不依赖 composition / evolution。

对应规格：doc/openspec/specs/orchestration/spec.md
"""

from .decomposer import Planner, SubtaskDecomposer, Verifier
from .errors import OrchestrationError, OrchestrationErrorCode
from .models import (
    AgentProfile,
    DecomposeResult,
    Plan,
    Subtask,
    TaskHandoff,
    TaskState,
    VerifyResult,
    plan_from_dict,
    plan_to_dict,
)
from .planner import LLMSubtaskPlanner, LLMTaskVerifier, LLMVerifier
from .router import MultiAgentRouter
from .scheduler import ProgressTracker, SubtaskOutcome, SuccessChecker, TaskScheduler
from .state_machine import StateMachine

__all__ = [
    "AgentProfile",
    "DecomposeResult",
    "LLMSubtaskPlanner",
    "LLMTaskVerifier",
    "LLMVerifier",
    "MultiAgentRouter",
    "OrchestrationError",
    "OrchestrationErrorCode",
    "Plan",
    "Planner",
    "ProgressTracker",
    "StateMachine",
    "Subtask",
    "SubtaskDecomposer",
    "SubtaskOutcome",
    "SuccessChecker",
    "TaskHandoff",
    "TaskScheduler",
    "TaskState",
    "Verifier",
    "VerifyResult",
    "plan_from_dict",
    "plan_to_dict",
]
