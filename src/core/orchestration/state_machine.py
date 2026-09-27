"""任务状态机（orchestration）。

显式状态机管理任务状态，只允许合法状态转移（迁移表显式建模），非法转移
抛 ``INVALID_TRANSITION``；任意活跃态可经熔断 / 人工终止转入 ``FAILED``。

对应接口：doc/03-interfaces/orchestration-interface.md §1
"""

from __future__ import annotations

from .errors import OrchestrationError, OrchestrationErrorCode
from .models import TaskState


class StateMachine:
    """任务状态机：迁移表驱动的显式状态管理。"""

    _TRANSITIONS: dict[TaskState, set[TaskState]] = {
        TaskState.CREATED: {TaskState.PLANNING, TaskState.FAILED},
        TaskState.PLANNING: {TaskState.EXECUTING, TaskState.FAILED},
        TaskState.EXECUTING: {TaskState.VERIFYING, TaskState.SUSPENDED, TaskState.FAILED},
        TaskState.VERIFYING: {
            TaskState.EXECUTING,
            TaskState.DONE,
            TaskState.RECOVERING,
            TaskState.FAILED,
        },
        TaskState.SUSPENDED: {TaskState.EXECUTING, TaskState.FAILED},
        TaskState.RECOVERING: {TaskState.EXECUTING, TaskState.FAILED},
        TaskState.DONE: set(),
        TaskState.FAILED: set(),
    }

    def __init__(self) -> None:
        self._states: dict[str, TaskState] = {}

    def transition(self, task_id: str, to: TaskState) -> None:
        """执行合法状态转移；非法转移抛 ``INVALID_TRANSITION``。"""
        current = self.state(task_id)
        if to not in self._TRANSITIONS[current]:
            raise OrchestrationError(
                OrchestrationErrorCode.INVALID_TRANSITION,
                f"非法状态转移: {current.value} → {to.value}",
            )
        self._states[task_id] = to

    def state(self, task_id: str) -> TaskState:
        """返回任务当前状态；未登记任务缺省 ``CREATED``。"""
        return self._states.get(task_id, TaskState.CREATED)
