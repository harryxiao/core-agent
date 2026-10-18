"""任务编排领域错误码（orchestration）。

结构化错误码与异常分离：非法转移 / 校验失败 / 执行失败 / 死循环 / 无匹配 Agent /
并行度超限 / 调度策略非法 / 进度未达标 / 判定器缺失，以领域异常承载，
不向模型抛裸异常。

对应接口：doc/03-interfaces/orchestration-interface.md §4
"""

from __future__ import annotations

from enum import StrEnum


class OrchestrationErrorCode(StrEnum):
    """编排结构化错误码。"""

    INVALID_TRANSITION = "INVALID_TRANSITION"
    SUBTASK_VERIFY_FAILED = "SUBTASK_VERIFY_FAILED"
    SUBTASK_EXECUTION_FAILED = "SUBTASK_EXECUTION_FAILED"
    SUBTASK_TIMEOUT = "SUBTASK_TIMEOUT"
    DEADLOOP_DETECTED = "DEADLOOP_DETECTED"
    NO_AGENT_MATCH = "NO_AGENT_MATCH"
    WAVE_FANOUT_LIMIT = "WAVE_FANOUT_LIMIT"
    INVALID_DISPATCH_POLICY = "INVALID_DISPATCH_POLICY"
    PROGRESS_NOT_MET = "PROGRESS_NOT_MET"
    MISSING_SUCCESS_CHECKER = "MISSING_SUCCESS_CHECKER"
    TASK_CANCELLED = "TASK_CANCELLED"
    BACKGROUND_TASKS_FULL = "BACKGROUND_TASKS_FULL"
    # 子 Agent 工作树隔离（change 0284）：无法创建隔离工作区。
    WORKTREE_UNAVAILABLE = "WORKTREE_UNAVAILABLE"
    # 无人值守护栏（change 0280）：整任务墙钟超时 / token 预算耗尽。
    TASK_TIMEOUT = "TASK_TIMEOUT"
    TASK_TOKEN_BUDGET_EXCEEDED = "TASK_TOKEN_BUDGET_EXCEEDED"


class OrchestrationError(Exception):
    """编排业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: OrchestrationErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
