"""并行扇出调度器与目标进度追踪（orchestration）。

波次内子任务异步扇出（真并发，受资源上限约束分批），fan-in 汇总校验；
目标进度追踪 + 死循环哨兵；挂起 / 恢复 / 取消断点续跑。子任务按优先级
降序调度（同优先级稳定序 FIFO），已完成子任务幂等跳过。run 为同步语义
收口（失败按原错误码抛错），astream 流式外发任务进度事件（含子任务**运行态**
回流 `subtask_progress`：里程碑事件按白名单转译），拆解 / 验收 / 检查点 /
终态等关键节点写 trace 审计。

对应接口：doc/03-interfaces/orchestration-interface.md §1（断点续跑）§2.2
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, cast

from core.loop import LoopEvent, collect_result
from core.observability import TraceEvent, Tracer

from .decomposer import SubtaskDecomposer
from .errors import OrchestrationError, OrchestrationErrorCode
from .models import Plan, Subtask, TaskState
from .router import MultiAgentRouter
from .state_machine import StateMachine

# 检查点回调：波次收拢后持久化（task_id、累计结果、全量计划——续跑重建用）。
CheckpointFn = Callable[[str, "list[SubtaskOutcome]", Plan], None]
# 完成回调：任务 DONE 后落终态检查点（done=True）。
DoneFn = Callable[[str, "list[SubtaskOutcome]", Plan], None]
# 子任务事件发射器：入队即返回（None 为波次收尾哨兵）。
Emit = Callable[[LoopEvent | None], None]

_MAX_HANDOFF_CHARS = 2000  # 依赖结果注入/检查点留存的回复截断（上下文有界）
_MAX_EVENT_EXCERPT = 600  # 进度事件携带的回复节选（UI 折叠详情用）

# 同波次调度策略取值（change 0123；词表来源：doc/openspec/specs/orchestration/spec.md）：
#   off（缺省）  —— 同波次按依赖拓扑并发（上限 max_concurrency），与引入策略前逐字一致；
#   difficulty —— 同波次**含 hard** 时该波次串行，否则维持并发
#                 （难易度是**降级信号**，不是并发开关）。
DISPATCH_POLICIES: frozenset[str] = frozenset({"off", "difficulty"})

# 子任务运行态回流白名单：内层循环事件类型 → 允许外发的载荷键。
# **白名单封闭**：表内没有的类型（含模型流式原文 `reply_delta` 与未来新增类型）一律不外发
# —— 既不洪泛，也不把未定稿原文/凭据带进事件面（「密钥只引用不读取」）。
_PROGRESS_FIELDS: dict[str, tuple[str, ...]] = {
    "action_started": ("round", "tool_id", "args"),
    "action_completed": ("round", "tool_id", "ok", "duration_ms", "output"),
    "step_completed": ("round", "failed"),
}


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
    """子任务执行结果：通过与否 + 结构化错误码 + 原因 + 追溯 trace + 回复摘要。

    reply 携带验收通过的结果（截断有界），供依赖子任务交接与检查点续跑重建。
    """

    subtask_id: str
    ok: bool
    error: OrchestrationErrorCode | None = None
    reason: str = ""
    trace_id: str = ""
    reply: str = ""


class TaskScheduler:
    """波次并行扇出调度器：fan-out（真并发）+ fan-in（汇总校验）+ 断点续跑。"""

    def __init__(  # noqa: PLR0913 — 调度依赖与策略均为构造注入
        self,
        *,
        decomposer: SubtaskDecomposer,
        router: MultiAgentRouter,
        state_machine: StateMachine,
        tracker: ProgressTracker | None = None,
        max_concurrency: int = 4,
        difficulty_policy: str = "off",
        success_checker: Callable[[list[str]], bool] | None = None,
        checkpoint: CheckpointFn | None = None,
        on_done: DoneFn | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        if max_concurrency < 1:
            raise OrchestrationError(
                OrchestrationErrorCode.WAVE_FANOUT_LIMIT,
                f"并行度上限须 ≥1，当前 {max_concurrency}",
            )
        if difficulty_policy not in DISPATCH_POLICIES:
            raise OrchestrationError(
                OrchestrationErrorCode.INVALID_DISPATCH_POLICY,
                f"非法调度策略: {difficulty_policy}（可选：{'/'.join(sorted(DISPATCH_POLICIES))}）",
            )
        self._decomposer = decomposer
        self._router = router
        self._state_machine = state_machine
        self._tracker = tracker if tracker is not None else ProgressTracker()
        self._max_concurrency = max_concurrency
        self._difficulty_policy = difficulty_policy
        self._success_checker = success_checker
        self._checkpoint = checkpoint
        self._on_done = on_done
        self._tracer = tracer
        self._results: dict[str, dict[str, str]] = {}  # task_id → subtask_id → 验收通过的回复

    async def run(  # noqa: PLR0913 — 续跑注入面（plan/completed/results）
        self,
        task_id: str,
        goal: str,
        success_criteria: list[str] | None = None,
        *,
        plan: Plan | None = None,
        completed: set[str] | None = None,
        results: dict[str, str] | None = None,
        session_id: str = "",
    ) -> list[SubtaskOutcome]:
        """同步语义收口：消费 astream；终态失败按原错误码抛 OrchestrationError。

        plan / completed / results 为断点续跑注入面：跳过拆解、跳过已完成
        子任务、重建依赖结果上下文。``session_id`` 为发起方会话标识（缺省空串 =
        未归属），透传至子 Agent 执行 ⇒ 子任务轨迹按发起会话归属。
        """
        async for event in self.astream(
            task_id,
            goal,
            success_criteria,
            plan=plan,
            completed=completed,
            results=results,
            session_id=session_id,
        ):
            if event.type == "task_failed":
                data = cast(dict[str, Any], event.payload)
                raise OrchestrationError(data["code"], data["reason"])
            if event.type == "task_finished":
                data = cast(dict[str, Any], event.payload)
                return cast(list[SubtaskOutcome], data["outcomes"])
        # astream 必达终态（finished/failed），此处为防御性兜底
        raise OrchestrationError(
            OrchestrationErrorCode.PROGRESS_NOT_MET, "任务流意外终止（未达终态）"
        )

    async def astream(  # noqa: C901, PLR0912, PLR0913, PLR0915 — 编排主管线多分支长管道
        self,
        task_id: str,
        goal: str,
        success_criteria: list[str] | None = None,
        *,
        plan: Plan | None = None,
        completed: set[str] | None = None,
        results: dict[str, str] | None = None,
        session_id: str = "",
    ) -> AsyncIterator[LoopEvent]:
        """流式任务执行：拆解 → 波次扇出 → 验收推进，进度事件依序外发。"""
        yield LoopEvent("task_started", {"task_id": task_id, "goal": goal})
        for subtask_id in completed or set():
            self._tracker.record(task_id, subtask_id)  # 续跑：已完成集回填
        if results:
            self._results.setdefault(task_id, {}).update(results)  # 续跑：依赖上下文重建
        if plan is None:
            try:
                plan = await self._decomposer.decompose(goal, success_criteria)
            except OrchestrationError as exc:
                self._trace(task_id, "task_failed", {"reason": str(exc)})
                yield LoopEvent(
                    "task_failed", {"task_id": task_id, "code": exc.code, "reason": str(exc)}
                )
                return
        self._trace(
            task_id, "plan_ready", {"subtasks": [s.id for s in plan.subtasks], "waves": plan.waves}
        )
        yield LoopEvent(
            "plan_ready",
            {
                "task_id": task_id,
                "goal": plan.goal,
                "subtasks": [
                    {
                        "id": s.id,
                        "goal": s.goal,
                        "acceptance": s.acceptance,
                        "depends_on": list(s.depends_on),
                    }
                    for s in plan.subtasks
                ],
                "waves": [list(w) for w in plan.waves],
            },
        )
        self._enter_executing(task_id)
        outcomes: list[SubtaskOutcome] = []
        for wave in plan.waves:
            yield LoopEvent("wave_started", {"task_id": task_id, "wave": list(wave)})
            queue: asyncio.Queue[LoopEvent | None] = asyncio.Queue()
            gather_task = asyncio.create_task(
                self._fan_out(task_id, plan, wave, queue.put_nowait, session_id=session_id)
            )
            while True:  # 排水子任务事件（None 哨兵 = 波次收拢）
                event = await queue.get()
                if event is None:
                    break
                yield event
            await gather_task  # fan-out 异常在此重放（fan-in 语义不变）
            wave_outcomes = gather_task.result()
            outcomes.extend(wave_outcomes)
            self._state_machine.transition(task_id, TaskState.VERIFYING)
            failed = [o.subtask_id for o in wave_outcomes if not o.ok]
            if failed:
                self._state_machine.transition(task_id, TaskState.RECOVERING)
                yield self._failed(
                    task_id,
                    OrchestrationErrorCode.SUBTASK_VERIFY_FAILED,
                    f"子任务校验失败: {failed}",
                    failed=failed,
                )
                return
            if self._tracker.detect_stall(task_id):
                self._state_machine.transition(task_id, TaskState.RECOVERING)
                yield self._failed(
                    task_id,
                    OrchestrationErrorCode.DEADLOOP_DETECTED,
                    f"任务 {task_id} 检测到死循环（进度无推进）",
                )
                return
            if self._checkpoint is not None:
                self._checkpoint(task_id, outcomes, plan)
                yield LoopEvent(
                    "task_checkpoint",
                    {
                        "task_id": task_id,
                        "wave": list(wave),
                        "completed": sorted(self._tracker.completed(task_id)),
                    },
                )
                self._trace(task_id, "task_checkpoint", {"wave": list(wave)})
            self._state_machine.transition(task_id, TaskState.EXECUTING)
        self._state_machine.transition(task_id, TaskState.VERIFYING)
        if plan.success_criteria and self._success_checker is None:
            self._state_machine.transition(task_id, TaskState.FAILED)
            yield self._failed(
                task_id,
                OrchestrationErrorCode.MISSING_SUCCESS_CHECKER,
                f"任务 {task_id} 提供了 success_criteria 但未注入 success_checker",
            )
            return
        if not self._success_met(plan.success_criteria):
            self._state_machine.transition(task_id, TaskState.RECOVERING)
            yield self._failed(
                task_id,
                OrchestrationErrorCode.PROGRESS_NOT_MET,
                f"任务 {task_id} 未达成成功标准: {plan.success_criteria}",
            )
            return
        self._state_machine.transition(task_id, TaskState.DONE)
        if self._on_done is not None:
            self._on_done(task_id, outcomes, plan)
        self._trace(
            task_id,
            "task_finished",
            {"ok": sum(1 for o in outcomes if o.ok), "total": len(outcomes)},
        )
        yield LoopEvent("task_finished", {"task_id": task_id, "outcomes": outcomes})

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

    def _failed(
        self,
        task_id: str,
        code: OrchestrationErrorCode,
        reason: str,
        *,
        failed: list[str] | None = None,
    ) -> LoopEvent:
        """失败收口：trace + task_failed 事件（run 消费端还原为抛错）。"""
        self._trace(task_id, "task_failed", {"code": str(code), "reason": reason})
        payload: dict[str, Any] = {"task_id": task_id, "code": code, "reason": reason}
        if failed:
            payload["failed"] = failed
        return LoopEvent("task_failed", payload)

    def _success_met(self, criteria: list[str]) -> bool:
        """成功标准判定：空标准视为通过；否则调用注入的 checker（缺失已在 run 入口校验）。"""
        if not criteria:
            return True
        assert self._success_checker is not None  # astream 已拦截缺失场景
        return self._success_checker(criteria)

    def _enter_executing(self, task_id: str) -> None:
        """新任务 CREATED→PLANNING→EXECUTING；挂起/已执行任务直接进 EXECUTING。"""
        state = self._state_machine.state(task_id)
        if state == TaskState.CREATED:
            self._state_machine.transition(task_id, TaskState.PLANNING)
            self._state_machine.transition(task_id, TaskState.EXECUTING)
        elif state == TaskState.SUSPENDED:
            self._state_machine.transition(task_id, TaskState.EXECUTING)

    async def _fan_out(
        self, task_id: str, plan: Plan, wave: list[str], emit: Emit, *, session_id: str = ""
    ) -> list[SubtaskOutcome]:
        """波次内子任务优先级排序 + 真并发扇出（资源上限分批）+ 汇总。"""
        subtasks = [s for s in plan.subtasks if s.id in wave]
        ordered = sorted(subtasks, key=lambda s: s.priority, reverse=True)
        semaphore = asyncio.Semaphore(self._wave_limit(ordered))
        try:
            outcomes = await asyncio.gather(
                *(
                    self._run_subtask(
                        task_id, plan, subtask, semaphore, emit, session_id=session_id
                    )
                    for subtask in ordered
                )
            )
            return list(outcomes)
        finally:
            emit(None)  # 收尾哨兵：异常路径也必须解除事件排水阻塞

    def _wave_limit(self, subtasks: list[Subtask]) -> int:
        """本波次并发度（change 0123 难易度感知调度策略）。

        ``off``（缺省）⇒ 资源上限（与引入策略前逐字一致）；``difficulty`` 且本波次**存在**
        `hard` 子任务 ⇒ ``1``（串行逐个，避免资源争抢/上下文污染）。策略只**收窄**、不放大：
        无任何一种取值会让并发高于 `max_concurrency`。
        """
        if self._difficulty_policy == "difficulty" and any(
            s.difficulty == "hard" for s in subtasks
        ):
            return 1
        return self._max_concurrency

    async def _run_subtask(  # noqa: PLR0911, PLR0913 — 子任务管道多早退分支/注入面
        self,
        task_id: str,
        plan: Plan,
        subtask: Subtask,
        semaphore: asyncio.Semaphore,
        emit: Emit,
        *,
        session_id: str = "",
    ) -> SubtaskOutcome:
        """执行单个子任务：幂等跳过已完成 → 匹配 Agent → 异步执行 → 验收门。

        ``session_id`` 为发起方会话标识（缺省空串 = 未归属），透传至子 Agent 执行。
        """
        if subtask.id in self._tracker.completed(task_id):
            emit(
                LoopEvent(
                    "subtask_completed",
                    {"task_id": task_id, "subtask_id": subtask.id, "ok": True, "skipped": True},
                )
            )
            return SubtaskOutcome(subtask.id, ok=True)
        emit(
            LoopEvent(
                "subtask_started",
                {
                    "task_id": task_id,
                    "subtask_id": subtask.id,
                    "goal": subtask.goal,
                    "acceptance": subtask.acceptance,
                },
            )
        )
        async with semaphore:
            try:
                profile = self._router.match(subtask.goal)
            except OrchestrationError:
                profile = None
            if profile is None or profile.loop is None:
                emit(
                    LoopEvent(
                        "subtask_completed",
                        {
                            "task_id": task_id,
                            "subtask_id": subtask.id,
                            "ok": False,
                            "reason": "无匹配 Agent",
                        },
                    )
                )
                return SubtaskOutcome(
                    subtask.id,
                    ok=False,
                    error=OrchestrationErrorCode.NO_AGENT_MATCH,
                    reason="无匹配 Agent",
                )
            goal = self._handoff_goal(task_id, plan, subtask)
            # 子任务轨迹按**发起方会话**归属（缺省空串 = 未归属）⇒ 非空才传第二实参
            stream = (
                profile.loop.astream(goal, session_id=session_id)
                if session_id
                else profile.loop.astream(goal)
            )
            # 流式执行：里程碑事件实时回流，终态仍归一为 LoopResult（附加通道，不改判定）
            result = await collect_result(
                stream, lambda event: self._emit_progress(task_id, subtask.id, event, emit)
            )
            verify = await self._decomposer.verify(subtask, result.reply)
            self._trace(
                task_id,
                "subtask_verified",
                {"subtask_id": subtask.id, "passed": verify.passed, "reason": verify.reason},
            )
            emit(
                LoopEvent(
                    "subtask_completed",
                    {
                        "task_id": task_id,
                        "subtask_id": subtask.id,
                        "ok": verify.passed,
                        "reason": verify.reason,
                        "trace_id": result.trace_id,
                        "reply": result.reply[:_MAX_EVENT_EXCERPT],
                    },
                )
            )
            if verify.passed:
                self._tracker.record(task_id, subtask.id)
                self._results.setdefault(task_id, {})[subtask.id] = result.reply[
                    :_MAX_HANDOFF_CHARS
                ]
                return SubtaskOutcome(
                    subtask.id,
                    ok=True,
                    trace_id=result.trace_id,
                    reply=result.reply[:_MAX_HANDOFF_CHARS],
                )
            return SubtaskOutcome(
                subtask.id,
                ok=False,
                error=OrchestrationErrorCode.SUBTASK_VERIFY_FAILED,
                reason=verify.reason,
                trace_id=result.trace_id,
            )

    def _emit_progress(self, task_id: str, subtask_id: str, event: LoopEvent, emit: Emit) -> None:
        """里程碑事件按白名单转译为 `subtask_progress`；表外类型与非字典载荷**静默丢弃**。"""
        fields = _PROGRESS_FIELDS.get(event.type)
        raw = event.payload
        if fields is None or not isinstance(raw, dict):
            return
        payload = cast("dict[str, Any]", raw)
        emit(
            LoopEvent(
                "subtask_progress",
                {
                    "task_id": task_id,
                    "subtask_id": subtask_id,
                    "event": event.type,
                    "data": {key: payload[key] for key in fields if key in payload},
                    "ts": time.time(),
                },
            )
        )

    def _handoff_goal(self, task_id: str, plan: Plan, subtask: Subtask) -> str:
        """交接目标：子任务 goal + 前置依赖的验收通过结果（结果驱动后继）。"""
        results = self._results.get(task_id, {})
        by_id = {s.id: s for s in plan.subtasks}
        deps = [dep for dep in subtask.depends_on if dep in results]
        if not deps:
            return subtask.goal
        context = "\n\n".join(
            f"[前置子任务 {dep}] {by_id[dep].goal if dep in by_id else ''}\n结果：{results[dep]}"
            for dep in deps
        )
        return f"{subtask.goal}\n\n前置子任务结果（可直接引用）：\n{context}"

    def _trace(self, task_id: str, kind: str, payload: dict[str, Any] | None = None) -> None:
        """关键节点写 trace（拆解/验收/检查点/终态——审计与断点续跑可查）。"""
        if self._tracer is None:
            return
        self._tracer.record(
            TraceEvent(
                trace_id=task_id,
                span_id=uuid.uuid4().hex,
                ts=time.time(),
                kind=kind,
                payload=payload or {},
            )
        )
