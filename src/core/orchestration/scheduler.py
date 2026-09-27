"""并行扇出调度器与目标进度追踪（orchestration）。

波次内子任务异步扇出（真并发，受资源上限约束分批），fan-in 汇总校验；
目标进度追踪 + 死循环哨兵；挂起 / 恢复 / 取消断点续跑。子任务按优先级
降序调度（同优先级稳定序 FIFO），已完成子任务幂等跳过。

对应接口：doc/03-interfaces/orchestration-interface.md §1（断点续跑场景）
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .decomposer import SubtaskDecomposer
from .errors import OrchestrationError, OrchestrationErrorCode
from .models import Plan, Subtask, TaskState
from .router import MultiAgentRouter
from .state_machine import StateMachine


class ProgressTracker:
    """目标进度追踪 + 死循环哨兵：按进度签名重复检测无推进。"""

    def __init__(self, *, stall_limit: int = 3) -> None:
        self._completed: dict[str, set[str]] = {}
        self._signatures: dict[str, list[tuple[str, ...]]] = {}
        self._stall_limit = stall_limit

    def record(self, task_id: str, subtask_id: str) -> None:
        """记录子任务完成，推进进度。"""
        self._completed.setdefault(task_id, set()).add(subtask_id)

    def completed(self, task_id: str) -> set[str]:
        """返回任务已完成的子任务 id 集合。"""
        return set(self._completed.get(task_id, set()))

    def detect_stall(self, task_id: str) -> bool:
        """记录当前进度签名，最近 ``stall_limit`` 次签名一致 → 无推进 → 死循环。"""
        signature = tuple(sorted(self._completed.get(task_id, set())))
        history = self._signatures.setdefault(task_id, [])
        history.append(signature)
        if len(history) < self._stall_limit:
            return False
        return len(set(history[-self._stall_limit :])) == 1

    def reset(self, task_id: str) -> None:
        """清空任务进度（取消 / 重建时）。"""
        self._completed.pop(task_id, None)
        self._signatures.pop(task_id, None)


@dataclass
class SubtaskOutcome:
    """子任务执行结果：通过与否 + 结构化错误码 + 原因。"""

    subtask_id: str
    ok: bool
    error: OrchestrationErrorCode | None = None
    reason: str = ""


class TaskScheduler:
    """波次并行扇出调度器：fan-out（真并发）+ fan-in（汇总校验）+ 断点续跑。"""

    def __init__(
        self,
        *,
        decomposer: SubtaskDecomposer,
        router: MultiAgentRouter,
        state_machine: StateMachine,
        tracker: ProgressTracker | None = None,
        max_concurrency: int = 4,
    ) -> None:
        if max_concurrency < 1:
            raise OrchestrationError(
                OrchestrationErrorCode.WAVE_FANOUT_LIMIT,
                f"并行度上限须 ≥1，当前 {max_concurrency}",
            )
        self._decomposer = decomposer
        self._router = router
        self._state_machine = state_machine
        self._tracker = tracker if tracker is not None else ProgressTracker()
        self._max_concurrency = max_concurrency

    async def run(self, task_id: str, goal: str) -> list[SubtaskOutcome]:
        """拆解 → 波次并行扇出 → fan-in 校验推进，直至完成或失败。"""
        plan = self._decomposer.decompose(goal)
        self._enter_executing(task_id)
        outcomes: list[SubtaskOutcome] = []
        for wave in plan.waves:
            wave_outcomes = await self._fan_out(task_id, plan, wave)
            outcomes.extend(wave_outcomes)
            self._state_machine.transition(task_id, TaskState.VERIFYING)
            failed = [o.subtask_id for o in wave_outcomes if not o.ok]
            if failed:
                self._state_machine.transition(task_id, TaskState.RECOVERING)
                raise OrchestrationError(
                    OrchestrationErrorCode.SUBTASK_VERIFY_FAILED,
                    f"子任务校验失败: {failed}",
                )
            if self._tracker.detect_stall(task_id):
                self._state_machine.transition(task_id, TaskState.RECOVERING)
                raise OrchestrationError(
                    OrchestrationErrorCode.DEADLOOP_DETECTED,
                    f"任务 {task_id} 检测到死循环（进度无推进）",
                )
            self._state_machine.transition(task_id, TaskState.EXECUTING)
        self._state_machine.transition(task_id, TaskState.VERIFYING)
        self._state_machine.transition(task_id, TaskState.DONE)
        return outcomes

    def suspend(self, task_id: str) -> None:
        """挂起：持久化执行上下文（进度已留存于 tracker）并转入 SUSPENDED。"""
        self._state_machine.transition(task_id, TaskState.SUSPENDED)

    def resume(self, task_id: str) -> None:
        """恢复：从断点继续（已完成子任务幂等跳过，不重复执行）。"""
        self._state_machine.transition(task_id, TaskState.EXECUTING)

    def cancel(self, task_id: str) -> None:
        """取消：转入 FAILED 并释放进度上下文。"""
        self._state_machine.transition(task_id, TaskState.FAILED)
        self._tracker.reset(task_id)

    def _enter_executing(self, task_id: str) -> None:
        """新任务 CREATED→PLANNING→EXECUTING；挂起/已执行任务直接进 EXECUTING。"""
        state = self._state_machine.state(task_id)
        if state == TaskState.CREATED:
            self._state_machine.transition(task_id, TaskState.PLANNING)
            self._state_machine.transition(task_id, TaskState.EXECUTING)
        elif state == TaskState.SUSPENDED:
            self._state_machine.transition(task_id, TaskState.EXECUTING)

    async def _fan_out(self, task_id: str, plan: Plan, wave: list[str]) -> list[SubtaskOutcome]:
        """波次内子任务优先级排序 + 真并发扇出（资源上限分批）+ 汇总。"""
        subtasks = [s for s in plan.subtasks if s.id in wave]
        ordered = sorted(subtasks, key=lambda s: s.priority, reverse=True)
        semaphore = asyncio.Semaphore(self._max_concurrency)
        outcomes = await asyncio.gather(
            *(self._run_subtask(task_id, subtask, semaphore) for subtask in ordered)
        )
        return list(outcomes)

    async def _run_subtask(
        self, task_id: str, subtask: Subtask, semaphore: asyncio.Semaphore
    ) -> SubtaskOutcome:
        """执行单个子任务：幂等跳过已完成 → 匹配 Agent → 异步执行 → 校验。"""
        if subtask.id in self._tracker.completed(task_id):
            return SubtaskOutcome(subtask.id, ok=True)
        async with semaphore:
            profile = self._router.match(subtask.goal)
            if profile is None or profile.loop is None:
                return SubtaskOutcome(
                    subtask.id,
                    ok=False,
                    error=OrchestrationErrorCode.NO_AGENT_MATCH,
                    reason="无匹配 Agent",
                )
            result = await profile.loop.arun(subtask.goal)
            verify = self._decomposer.verify(subtask, result.reply)
            if verify.passed:
                self._tracker.record(task_id, subtask.id)
                return SubtaskOutcome(subtask.id, ok=True)
            return SubtaskOutcome(
                subtask.id,
                ok=False,
                error=OrchestrationErrorCode.SUBTASK_VERIFY_FAILED,
                reason=verify.reason,
            )
