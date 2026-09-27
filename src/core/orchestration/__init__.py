"""多 Agent 任务编排（orchestration，L4 编排层）。

任务状态机 + 子任务拆解 + 多 Agent 协同 + 并行扇出调度 + 断点续跑，
向下依赖 loop / tools / llm-provider / durability / context / plugin-registry，
反向不依赖 composition / evolution。

对应规格：doc/openspec/specs/orchestration/spec.md
"""

from .decomposer import SubtaskDecomposer
from .errors import OrchestrationError, OrchestrationErrorCode
from .models import AgentProfile, Plan, Subtask, TaskHandoff, TaskState, VerifyResult
from .router import MultiAgentRouter
from .scheduler import ProgressTracker, SubtaskOutcome, TaskScheduler
from .state_machine import StateMachine

__all__ = [
    "AgentProfile",
    "MultiAgentRouter",
    "OrchestrationError",
    "OrchestrationErrorCode",
    "Plan",
    "ProgressTracker",
    "StateMachine",
    "Subtask",
    "SubtaskDecomposer",
    "SubtaskOutcome",
    "TaskHandoff",
    "TaskScheduler",
    "TaskState",
    "VerifyResult",
]
