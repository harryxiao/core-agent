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
import contextlib
import inspect
import json
import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from core.loop import LoopEvent, collect_result
from core.observability import TraceEvent, Tracer

from .decomposer import SubtaskDecomposer
from .errors import OrchestrationError, OrchestrationErrorCode
from .handoff import DEFAULT_CONTEXT_TOKENS, MAX_HANDOFF_CHARS, build_context_pack
from .models import Plan, Subtask, TaskHandoff, TaskState, VerifyResult, plan_to_dict
from .router import MultiAgentRouter
from .state_machine import StateMachine

# 检查点回调：波次收拢后持久化（task_id、累计结果、全量计划、发起会话标识——续跑重建用）。
# 第 4 参 session_id 为发起方会话标识（空串 = 未归属照实记录；change 0190 去占位值）。
CheckpointFn = Callable[[str, "list[SubtaskOutcome]", Plan, str], None]
# 完成回调：任务 DONE 后落终态检查点（done=True）；第 4参与检查点回调同口径。
DoneFn = Callable[[str, "list[SubtaskOutcome]", Plan, str], None]


@dataclass
class FileCheckpoint:
    """文件型检查点（change 0230 / G7）：满足 `CheckpointFn`，原子写单 JSON 文件。

    每次调用覆盖同一文件（单任务断点语义）：`task_id` / `session_id` / `plan`
    （`plan_to_dict`）/ 已完成子任务 id 与结果。写入经同目录临时文件 + `os.replace`
    原子替换，不留半写文件。**不**由调度器自动安装（缺省零 I/O，上层注入优先）。
    """

    path: str | Path = ".core/scheduler-checkpoint.json"

    def __call__(
        self, task_id: str, outcomes: list[SubtaskOutcome], plan: Plan, session_id: str
    ) -> None:
        payload = {
            "task_id": task_id,
            "session_id": session_id,
            "plan": plan_to_dict(plan),
            "completed": sorted(outcome.subtask_id for outcome in outcomes if outcome.ok),
            "results": {outcome.subtask_id: outcome.reply for outcome in outcomes if outcome.ok},
        }
        target = Path(self.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)

    def load(self, task_id: str | None = None) -> dict[str, Any] | None:
        """读取检查点（文件缺失/损坏/任务不匹配 ⇒ ``None``，不抛）。"""
        try:
            data = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        payload = cast(dict[str, Any], data)
        if task_id is not None and payload.get("task_id") != task_id:
            return None
        return payload


# 子任务事件发射器：入队即返回（None 为波次收尾哨兵）。
Emit = Callable[[LoopEvent | None], None]
# 任务级判定器：Goal + 成功标准 + 子任务结果 → 判定（支持异步，change 0248）。
SuccessChecker = Callable[
    [str, list[str], "list[SubtaskOutcome]"], VerifyResult | Awaitable[VerifyResult]
]

# 依赖结果注入/检查点留存的回复截断统一取 handoff.MAX_HANDOFF_CHARS（单点真源）
_MAX_EVENT_EXCERPT = 600  # 进度事件携带的回复节选（UI 折叠详情用）

# 失败恢复预算（change 0246）：任一子任务验收/执行失败 ⇒ 仅失败项重试 1 次；
# 仍失败 ⇒ 重新拆解 1 次；预算耗尽 ⇒ FAILED。固定策略，不做配置旋钮。
_MAX_SUBTASK_RETRIES = 1
_MAX_REPLANS = 1

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
    """目标进度追踪 + 死循环哨兵：三态进度（change 0248）与进度签名重复检测。"""

    def __init__(self, *, stall_limit: int = 3) -> None:
        self._completed: dict[str, set[str]] = {}
        self._started: dict[str, set[str]] = {}
        self._failed: dict[str, set[str]] = {}
        self._signatures: dict[str, list[tuple[str, ...]]] = {}
        self._stall_limit = stall_limit

    def start(self, task_id: str, subtask_id: str) -> None:
        """子任务开始派发（含重试）；重试开始即清除该子任务的失败标记。"""
        self._started.setdefault(task_id, set()).add(subtask_id)
        self._failed.get(task_id, set()).discard(subtask_id)

    def fail(self, task_id: str, subtask_id: str) -> None:
        """子任务失败待恢复（重试成功或重新拆解后清除）。"""
        self._failed.setdefault(task_id, set()).add(subtask_id)

    def record(self, task_id: str, subtask_id: str) -> None:
        """记录子任务完成，推进进度并清除失败标记。"""
        self._completed.setdefault(task_id, set()).add(subtask_id)
        self._failed.get(task_id, set()).discard(subtask_id)

    def completed(self, task_id: str) -> set[str]:
        """返回任务已完成的子任务 id 集合。"""
        return set(self._completed.get(task_id, set()))

    def progress(self, task_id: str) -> dict[str, int]:
        """三态计数：已开始 / 已完成 / 失败待恢复（按子任务去重）。"""
        return {
            "started": len(self._started.get(task_id, set())),
            "completed": len(self._completed.get(task_id, set())),
            "failed": len(self._failed.get(task_id, set())),
        }

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
        self._started.pop(task_id, None)
        self._failed.pop(task_id, None)
        self._signatures.pop(task_id, None)


@dataclass
class SubtaskOutcome:
    """子任务执行结果：通过与否 + 结构化错误码 + 原因 + 追溯 trace + 回复摘要。

    reply 携带验收通过的结果（截断有界），供依赖子任务交接与检查点续跑重建。
    attempt 为本次结果的执行序号（1 = 首发，2 = 重试），用于终态计数与可观测性。
    """

    subtask_id: str
    ok: bool
    error: OrchestrationErrorCode | None = None
    reason: str = ""
    trace_id: str = ""
    reply: str = ""
    attempt: int = 1


@dataclass
class _Failure:
    """恢复回路收口的一次失败：错误码 + 原因 + 失败项 + 已用尝试次数。"""

    code: OrchestrationErrorCode
    reason: str
    failed: list[str]
    attempts: int = 1


@dataclass
class _WaveResult:
    """波次执行收口：累计结果 + 该波次失败（None = 通过）。"""

    outcomes: list[SubtaskOutcome]
    failure: _Failure | None = None


def _merge_outcomes(
    outcomes: list[SubtaskOutcome], updates: list[SubtaskOutcome]
) -> list[SubtaskOutcome]:
    """按子任务 id 合并结果（重试以新结果覆盖旧结果，保留原顺序）。"""
    by_id = {outcome.subtask_id: outcome for outcome in outcomes}
    for outcome in updates:
        by_id[outcome.subtask_id] = outcome
    return list(by_id.values())


def _coerce_verdict(value: object) -> VerifyResult:
    """判定器返回值归一：非 ``VerifyResult`` 一律 fail-closed（外部注入边界）。"""
    if isinstance(value, VerifyResult):
        return value
    return VerifyResult(passed=False, reason="任务级判定器返回非法结果（fail-closed）")


def _failure_from(outcomes: list[SubtaskOutcome]) -> _Failure | None:
    """一轮结果聚合为失败收口；全部通过返回 None。"""
    failed = [outcome for outcome in outcomes if not outcome.ok]
    if not failed:
        return None
    last = failed[-1]
    return _Failure(
        code=last.error or OrchestrationErrorCode.SUBTASK_VERIFY_FAILED,
        reason=last.reason or f"子任务 {last.subtask_id} 执行失败",
        failed=[outcome.subtask_id for outcome in failed],
        attempts=last.attempt,
    )


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
        # 子任务交接超时（秒；`0` = 不设限）。构造缺省保持 `0`（不注入即不改变行为）；
        # 配置缺省 `600` 由组合根显式注入（change 0247 / 0260）。
        subtask_timeout: float = 0,
        # 整任务 token 预算（change 0280）：构造缺省 `0` = 关闭（不注入即不改变行为）；
        # 生产由组合根注入配置值。
        task_token_budget: int = 0,
        success_checker: SuccessChecker | None = None,
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
        if subtask_timeout < 0:
            raise OrchestrationError(
                OrchestrationErrorCode.INVALID_DISPATCH_POLICY,
                f"非法子任务超时: {subtask_timeout}（须为 ≥0 的秒数，0=不设限）",
            )
        if task_token_budget < 0:
            raise OrchestrationError(
                OrchestrationErrorCode.INVALID_DISPATCH_POLICY,
                f"非法整任务 token 预算: {task_token_budget}（须为 ≥0，0=关闭）",
            )
        self._decomposer = decomposer
        self._router = router
        self._state_machine = state_machine
        self._tracker = tracker if tracker is not None else ProgressTracker()
        self._max_concurrency = max_concurrency
        self._difficulty_policy = difficulty_policy
        self._subtask_timeout = subtask_timeout
        self._task_token_budget = task_token_budget
        self._success_checker = success_checker
        self._checkpoint = checkpoint
        self._on_done = on_done
        self._tracer = tracer
        self._results: dict[str, dict[str, str]] = {}  # task_id → subtask_id → 验收通过的回复
        # 整任务 token 累计（change 0280）：task_id → 各子任务 `LoopResult.token_used` 之和。
        self._task_tokens: dict[str, int] = {}
        # 运行中取消 / 断流登记（change 0249）：取消信号与当前波次的扇出任务，终态释放。
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._wave_tasks: dict[str, asyncio.Task[list[SubtaskOutcome]]] = {}

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

    async def astream(  # noqa: PLR0913 — 续跑注入面（plan/completed/results）
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
        """流式任务执行：拆解 → 波次扇出 → 验收推进 → 有限恢复，进度事件依序外发。

        任意退出路径（正常终态 / 取消 / 消费方断流 / 异常）经 `finally` 释放任务级上下文
        （change 0249）：在途扇出被取消、`_results` 与取消登记清空；未达终态转 `FAILED`。
        """
        try:
            async for event in self._stream_task(
                task_id,
                goal,
                success_criteria,
                plan=plan,
                completed=completed,
                results=results,
                session_id=session_id,
            ):
                yield event
        finally:
            self._release(task_id)

    async def _stream_task(  # noqa: C901, PLR0911, PLR0912, PLR0913, PLR0915 — 主管线多早退/多分支
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
        """主管线：由 `astream` 包装，负责取消观察与（正常/失败）终态事件。"""
        cancel_event = self._cancel_events.setdefault(task_id, asyncio.Event())
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
        if cancel_event.is_set():
            yield self._cancelled(task_id)
            return
        outcomes: list[SubtaskOutcome] = []
        while True:  # 恢复回路：重试 / 重拆后重入，预算耗尽才终止
            if cancel_event.is_set():
                yield self._cancelled(task_id)
                return
            if not plan.subtasks or not plan.waves:
                self._state_machine.transition(task_id, TaskState.FAILED)
                yield self._failed(
                    task_id,
                    OrchestrationErrorCode.SUBTASK_VERIFY_FAILED,
                    f"任务 {task_id} 的计划为空，无法执行",
                )
                return
            self._trace(
                task_id,
                "plan_ready",
                {
                    "subtasks": [s.id for s in plan.subtasks],
                    "waves": plan.waves,
                    "replan": plan.replans,
                },
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
                    "replan": plan.replans,
                },
            )
            self._enter_executing(task_id)
            failure: _Failure | None = None
            for wave in plan.waves:
                yield LoopEvent("wave_started", {"task_id": task_id, "wave": list(wave)})
                wave_result = _WaveResult(outcomes=outcomes)
                async for event in self._execute_wave(
                    task_id, plan, wave, session_id=session_id, result=wave_result
                ):
                    yield event
                if cancel_event.is_set():
                    yield self._cancelled(task_id)
                    return
                outcomes = wave_result.outcomes
                failure = wave_result.failure
                if failure is not None:
                    break
            if failure is None:
                self._state_machine.transition(task_id, TaskState.VERIFYING)
                if plan.success_criteria and self._success_checker is None:
                    self._state_machine.transition(task_id, TaskState.FAILED)
                    yield self._failed(
                        task_id,
                        OrchestrationErrorCode.MISSING_SUCCESS_CHECKER,
                        f"任务 {task_id} 提供了 success_criteria 但未注入 success_checker",
                    )
                    return
                verdict = await self._success_met(task_id, goal, plan, outcomes)
                if cancel_event.is_set():
                    yield self._cancelled(task_id)
                    return
                if not verdict.passed:
                    failure = _Failure(
                        OrchestrationErrorCode.PROGRESS_NOT_MET,
                        verdict.reason or f"任务 {task_id} 未达成成功标准: {plan.success_criteria}",
                        [],
                        attempts=max((o.attempt for o in outcomes), default=1),
                    )
            if failure is None:
                self._state_machine.transition(task_id, TaskState.DONE)
                if self._on_done is not None:
                    # 完成回调卸载出事件循环（change 0196）：回调可承载模型调用等重活，
                    # 不得在事件循环上同步阻塞（先例：loop/default.py change 0167 / ADR-0157）。
                    await asyncio.to_thread(self._on_done, task_id, outcomes, plan, session_id)
                self._trace(
                    task_id,
                    "task_finished",
                    {"ok": sum(1 for o in outcomes if o.ok), "total": len(outcomes)},
                )
                yield LoopEvent("task_finished", {"task_id": task_id, "outcomes": outcomes})
                return
            if failure.code is OrchestrationErrorCode.TASK_TOKEN_BUDGET_EXCEEDED:
                # 预算耗尽不重拆（change 0280）：新计划仍受同一累计值约束。
                self._state_machine.transition(task_id, TaskState.FAILED)
                yield self._failed(
                    task_id,
                    failure.code,
                    failure.reason,
                    extra={
                        "token_used": self._task_tokens.get(task_id, 0),
                        "token_budget": self._task_token_budget,
                    },
                )
                return
            if plan.replans >= _MAX_REPLANS:
                self._state_machine.transition(task_id, TaskState.FAILED)
                yield self._failed(
                    task_id,
                    failure.code,
                    failure.reason,
                    failed=failure.failed or None,
                    extra={"attempts": failure.attempts, "replans": plan.replans},
                )
                return
            # 重新拆解：先落计数与检查点（崩溃续跑不重置预算），再重入执行
            self._state_machine.transition(task_id, TaskState.RECOVERING)
            plan.replans += 1
            yield LoopEvent(
                "task_replanning",
                {
                    "task_id": task_id,
                    "replan": plan.replans,
                    "max_replans": _MAX_REPLANS,
                    "failed": failure.failed,
                    "reason": failure.reason,
                },
            )
            self._trace(task_id, "task_replanning", {"replan": plan.replans})
            if self._checkpoint is not None:
                self._checkpoint(task_id, outcomes, plan, session_id)
            replan_input = self._replan_input(task_id, goal, plan, failure)
            try:
                new_plan = await self._decomposer.decompose(replan_input)
            except OrchestrationError as exc:
                self._state_machine.transition(task_id, TaskState.FAILED)
                yield self._failed(
                    task_id,
                    exc.code,
                    f"重新拆解失败：{exc}",
                    extra={"replans": plan.replans},
                )
                return
            new_plan.goal = goal
            if plan.success_criteria:
                new_plan.success_criteria = list(plan.success_criteria)
            new_plan.replans = plan.replans
            # 新 DAG 可能复用 id：清空旧完成集/结果与累计 outcomes，避免误跳过与脏依赖
            self._tracker.reset(task_id)
            self._results.pop(task_id, None)
            outcomes = []
            plan = new_plan

    def suspend(self, task_id: str) -> None:
        """挂起：持久化执行上下文（进度已留存于 tracker）并转入 SUSPENDED。"""
        self._state_machine.transition(task_id, TaskState.SUSPENDED)

    def resume(self, task_id: str) -> None:
        """恢复：从断点继续（已完成子任务幂等跳过，不重复执行）。"""
        self._state_machine.transition(task_id, TaskState.EXECUTING)

    def cancel(self, task_id: str) -> None:
        """取消：置取消信号、打断在途扇出，转 FAILED 并释放进度上下文（change 0249）。

        终态任务重复取消**幂等**（不抛 `INVALID_TRANSITION`、不改状态与进度）；已持久化的
        断点上下文沿用既有策略保留。执行流观察到信号后以 `TASK_CANCELLED` 终止。
        """
        if self._state_machine.state(task_id) in (TaskState.DONE, TaskState.FAILED):
            return
        self._cancel_events.setdefault(task_id, asyncio.Event()).set()
        wave_task = self._wave_tasks.get(task_id)
        if wave_task is not None and not wave_task.done():
            wave_task.cancel()
        self._state_machine.transition(task_id, TaskState.FAILED)
        self._tracker.reset(task_id)
        self._results.pop(task_id, None)

    def _record_tokens(self, task_id: str, tokens: int) -> bool:
        """累计子任务 token 记账；返回本次累计是否达到正预算（change 0280）。

        预算为 `0` ⇒ 不记账、恒返回 False（关闭即零行为变化）。并发波次按各子任务
        **完成时**累加，可能小幅越过预算（不做跨协程预留）。
        """
        if self._task_token_budget <= 0:
            return False
        used = self._task_tokens.get(task_id, 0) + max(0, tokens)
        self._task_tokens[task_id] = used
        return used >= self._task_token_budget

    def _is_cancelled(self, task_id: str) -> bool:
        event = self._cancel_events.get(task_id)
        return event is not None and event.is_set()

    def _cancelled(self, task_id: str) -> LoopEvent:
        """取消终态事件（状态已由 `cancel` 转移，此处不重复转移）。"""
        reason = f"任务 {task_id} 已取消"
        self._trace(
            task_id,
            "task_failed",
            {"code": str(OrchestrationErrorCode.TASK_CANCELLED), "reason": reason},
        )
        return LoopEvent(
            "task_failed",
            {
                "task_id": task_id,
                "code": OrchestrationErrorCode.TASK_CANCELLED,
                "reason": reason,
            },
        )

    def _release(self, task_id: str) -> None:
        """任务流结束（任意原因）释放任务级上下文；未达终态转 FAILED（change 0249）。

        正常 `DONE` / `FAILED` 路径只做缓存释放，不动状态与进度；消费方断流 / 外部异常
        退出时按失败收口并 trace `task_aborted`（不伪装成功）。
        """
        cancelled = self._is_cancelled(task_id)
        self._cancel_events.pop(task_id, None)
        wave_task = self._wave_tasks.pop(task_id, None)
        if wave_task is not None and not wave_task.done():
            wave_task.cancel()
        self._results.pop(task_id, None)
        self._task_tokens.pop(task_id, None)
        if self._state_machine.state(task_id) in (TaskState.DONE, TaskState.FAILED):
            return
        self._state_machine.transition(task_id, TaskState.FAILED)
        self._tracker.reset(task_id)
        self._trace(
            task_id, "task_aborted", {"reason": "任务已取消" if cancelled else "消费方断流"}
        )

    def _failed(
        self,
        task_id: str,
        code: OrchestrationErrorCode,
        reason: str,
        *,
        failed: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> LoopEvent:
        """失败收口：trace + task_failed 事件（run 消费端还原为抛错）。"""
        self._trace(task_id, "task_failed", {"code": str(code), "reason": reason, **(extra or {})})
        payload: dict[str, Any] = {"task_id": task_id, "code": code, "reason": reason}
        if failed:
            payload["failed"] = failed
        if extra:
            payload.update(extra)
        return LoopEvent("task_failed", payload)

    async def _success_met(
        self, task_id: str, goal: str, plan: Plan, outcomes: list[SubtaskOutcome]
    ) -> VerifyResult:
        """任务级判定：空标准视为通过；checker 异常/非法返回 fail-closed（change 0248）。"""
        criteria = list(plan.success_criteria)
        if not criteria:
            return VerifyResult(passed=True, reason="")
        assert self._success_checker is not None  # astream 已拦截缺失场景
        try:
            # 防御性边界：checker 为外部注入，异常与非法返回一律 fail-closed
            raw = self._success_checker(goal, criteria, outcomes)
            verdict = _coerce_verdict(await raw if inspect.isawaitable(raw) else raw)
        except Exception:  # noqa: BLE001 — 判定器异常一律按未达标收口（不裸崩任务）
            verdict = VerifyResult(passed=False, reason="任务级判定器异常（fail-closed）")
        self._trace(
            task_id, "success_verdict", {"passed": verdict.passed, "reason": verdict.reason}
        )
        return verdict

    def _enter_executing(self, task_id: str) -> None:
        """新任务 CREATED→PLANNING→EXECUTING；挂起/恢复中任务直接进 EXECUTING。"""
        state = self._state_machine.state(task_id)
        if state == TaskState.CREATED:
            self._state_machine.transition(task_id, TaskState.PLANNING)
            self._state_machine.transition(task_id, TaskState.EXECUTING)
        elif state in (TaskState.SUSPENDED, TaskState.RECOVERING):
            self._state_machine.transition(task_id, TaskState.EXECUTING)

    async def _execute_wave(  # noqa: C901, PLR0913 — 波次执行注入面（会话/结果）
        self,
        task_id: str,
        plan: Plan,
        wave: list[str],
        *,
        session_id: str,
        result: _WaveResult,
    ) -> AsyncIterator[LoopEvent]:
        """执行一波次并完成重试收口；累计结果与失败写回 ``result``。"""
        wave_outcomes: list[SubtaskOutcome] = []
        async for event in self._stream_wave(
            task_id, plan, wave, session_id=session_id, sink=wave_outcomes
        ):
            yield event
        if self._is_cancelled(task_id):
            return  # 取消已置 FAILED：不做 VERIFYING 转移，避免非法转移
        outcomes = _merge_outcomes(result.outcomes, wave_outcomes)
        self._state_machine.transition(task_id, TaskState.VERIFYING)
        failure = _failure_from(wave_outcomes)
        if (
            failure is not None
            and failure.code is OrchestrationErrorCode.TASK_TOKEN_BUDGET_EXCEEDED
        ):
            # 预算耗尽不重试（change 0280）：重试只会继续烧预算。
            result.outcomes, result.failure = outcomes, failure
            return
        if failure is not None:
            self._state_machine.transition(task_id, TaskState.EXECUTING)
            retried: list[SubtaskOutcome] = []
            for retry_round in range(_MAX_SUBTASK_RETRIES):
                if failure is None:
                    break
                attempt = 2 + retry_round
                yield LoopEvent(
                    "task_retrying",
                    {
                        "task_id": task_id,
                        "attempt": attempt,
                        "failed": failure.failed,
                        "reason": failure.reason,
                    },
                )
                self._trace(
                    task_id, "task_retrying", {"attempt": attempt, "failed": failure.failed}
                )
                async for event in self._stream_wave(
                    task_id,
                    plan,
                    failure.failed,
                    session_id=session_id,
                    sink=retried,
                    attempt=attempt,
                    previous={sid: failure.reason for sid in failure.failed},
                ):
                    yield event
                outcomes = _merge_outcomes(outcomes, retried)
                failure = _failure_from(retried)
                if failure is not None:
                    failure.attempts = attempt
            self._state_machine.transition(task_id, TaskState.VERIFYING)
        if failure is not None:
            result.outcomes, result.failure = outcomes, failure
            return
        if self._tracker.detect_stall(task_id):
            result.outcomes = outcomes
            result.failure = _Failure(
                OrchestrationErrorCode.DEADLOOP_DETECTED,
                f"任务 {task_id} 检测到死循环（进度无推进）",
                [],
            )
            return
        if self._checkpoint is not None:
            self._checkpoint(task_id, outcomes, plan, session_id)
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
        result.outcomes = outcomes

    async def _stream_wave(  # noqa: PLR0913 — 波次执行注入面（会话/结果/重试）
        self,
        task_id: str,
        plan: Plan,
        wave: list[str],
        *,
        session_id: str,
        sink: list[SubtaskOutcome],
        attempt: int = 1,
        previous: dict[str, str] | None = None,
    ) -> AsyncIterator[LoopEvent]:
        """执行一个波次并排水子任务事件；收拢结果追加进 ``sink``（fan-in 语义不变）。

        扇出任务登记进 `_wave_tasks`，由 `cancel` / `_release` 统一打断（change 0249）；
        `finally` 只收拢已取消的扇出任务并注销登记，不再二次取消（单一清理归属）。
        """
        if self._is_cancelled(task_id):
            return  # 波次尚未开始即已取消：不再派发新子任务
        queue: asyncio.Queue[LoopEvent | None] = asyncio.Queue()
        gather_task = asyncio.create_task(
            self._fan_out(
                task_id,
                plan,
                wave,
                queue.put_nowait,
                session_id=session_id,
                attempt=attempt,
                previous=previous,
            )
        )
        self._wave_tasks[task_id] = gather_task
        try:
            while True:  # 排水子任务事件（None 哨兵 = 波次收拢）
                event = await queue.get()
                if event is None:
                    break
                yield event
            await gather_task  # fan-out 异常在此重放（守卫已把子任务异常归一为失败）
            sink.extend(gather_task.result())
        except asyncio.CancelledError:
            # 协作取消（`cancel` 已取消扇出任务）安静收拢；外部取消照常透传
            if not self._is_cancelled(task_id):
                raise
        finally:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await gather_task
            self._wave_tasks.pop(task_id, None)

    async def _fan_out(  # noqa: PLR0913 — 波次扇出注入面（会话/重试）
        self,
        task_id: str,
        plan: Plan,
        wave: list[str],
        emit: Emit,
        *,
        session_id: str = "",
        attempt: int = 1,
        previous: dict[str, str] | None = None,
    ) -> list[SubtaskOutcome]:
        """波次内子任务优先级排序 + 真并发扇出（资源上限分批）+ 汇总。"""
        subtasks = [s for s in plan.subtasks if s.id in wave]
        ordered = sorted(subtasks, key=lambda s: s.priority, reverse=True)
        semaphore = asyncio.Semaphore(self._wave_limit(ordered))
        try:
            outcomes = await asyncio.gather(
                *(
                    self._guarded_subtask(
                        task_id,
                        plan,
                        subtask,
                        semaphore,
                        emit,
                        session_id=session_id,
                        attempt=attempt,
                        previous_reason=(previous or {}).get(subtask.id, ""),
                    )
                    for subtask in ordered
                )
            )
            return list(outcomes)
        finally:
            emit(None)  # 收尾哨兵：异常路径也必须解除事件排水阻塞

    async def _guarded_subtask(  # noqa: PLR0913 — 子任务执行注入面（会话/重试）
        self,
        task_id: str,
        plan: Plan,
        subtask: Subtask,
        semaphore: asyncio.Semaphore,
        emit: Emit,
        *,
        session_id: str = "",
        attempt: int = 1,
        previous_reason: str = "",
    ) -> SubtaskOutcome:
        """子任务异常归一：结构化错误保留原码，其余异常 → SUBTASK_EXECUTION_FAILED。

        ``CancelledError`` 属 ``BaseException``，不在此捕获（取消必须透传）。
        """
        try:
            outcome = await self._run_subtask(
                task_id,
                plan,
                subtask,
                semaphore,
                emit,
                session_id=session_id,
                attempt=attempt,
                previous_reason=previous_reason,
            )
        except OrchestrationError as exc:
            outcome = self._failed_outcome(task_id, subtask.id, exc.code, str(exc), emit, attempt)
        except Exception as exc:  # noqa: BLE001 — 执行异常归一为子任务失败（不裸崩调度器）
            outcome = self._failed_outcome(
                task_id,
                subtask.id,
                OrchestrationErrorCode.SUBTASK_EXECUTION_FAILED,
                str(exc) or type(exc).__name__,
                emit,
                attempt,
            )
        if not outcome.ok:  # 三态进度：失败待恢复（重试开始 / 完成会清除）
            self._tracker.fail(task_id, subtask.id)
        return outcome

    def _failed_outcome(  # noqa: PLR0913, PLR0917 — 归一失败结果入参
        self,
        task_id: str,
        subtask_id: str,
        code: OrchestrationErrorCode,
        reason: str,
        emit: Emit,
        attempt: int,
    ) -> SubtaskOutcome:
        """异常归一后的失败结果（与常规验收失败同形，进入同一恢复回路）。"""
        emit(
            LoopEvent(
                "subtask_completed",
                {
                    "task_id": task_id,
                    "subtask_id": subtask_id,
                    "ok": False,
                    "reason": reason,
                    "attempt": attempt,
                },
            )
        )
        return SubtaskOutcome(subtask_id, ok=False, error=code, reason=reason, attempt=attempt)

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
        attempt: int = 1,
        previous_reason: str = "",
    ) -> SubtaskOutcome:
        """执行单个子任务：幂等跳过已完成 → 匹配 Agent → 异步执行 → 验收门。

        ``session_id`` 为发起方会话标识（缺省空串 = 未归属），透传至子 Agent 执行。
        ``attempt`` / ``previous_reason`` 为重试面（1 = 首发；>1 时把上次失败原因注入目标）。
        """
        if subtask.id in self._tracker.completed(task_id):
            emit(
                LoopEvent(
                    "subtask_completed",
                    {"task_id": task_id, "subtask_id": subtask.id, "ok": True, "skipped": True},
                )
            )
            return SubtaskOutcome(subtask.id, ok=True)
        self._tracker.start(task_id, subtask.id)  # 三态进度：派发即计入（重试清 failed）
        emit(
            LoopEvent(
                "subtask_started",
                {
                    "task_id": task_id,
                    "subtask_id": subtask.id,
                    "goal": subtask.goal,
                    "acceptance": subtask.acceptance,
                    "attempt": attempt,
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
                            "attempt": attempt,
                        },
                    )
                )
                return SubtaskOutcome(
                    subtask.id,
                    ok=False,
                    error=OrchestrationErrorCode.NO_AGENT_MATCH,
                    reason="无匹配 Agent",
                    attempt=attempt,
                )
            handoff = self._build_handoff(
                task_id,
                plan,
                subtask,
                session_id=session_id,
                attempt=attempt,
                previous_reason=previous_reason,
            )
            # 统一执行器：TaskHandoff 全字段消费（context_pack / acceptance / deadline /
            # priority / session_id；change 0247）。子任务轨迹按发起方会话归属。
            stream = self._router.handoff_stream(profile.agent_id, handoff)
            # 流式执行：里程碑事件实时回流，终态仍归一为 LoopResult（附加通道，不改判定）
            result = await collect_result(
                stream, lambda event: self._emit_progress(task_id, subtask.id, event, emit)
            )
            if self._record_tokens(task_id, result.token_used):
                # 整任务预算耗尽（change 0280）：即使验收本可通过也 fail-closed；
                # 调度器不在重试/重拆回路里再烧预算（见 _execute_wave / _stream_task）。
                reason = (
                    f"任务 {task_id} token 预算耗尽"
                    f"（{self._task_tokens.get(task_id, 0)}/{self._task_token_budget}）"
                )
                emit(
                    LoopEvent(
                        "subtask_completed",
                        {
                            "task_id": task_id,
                            "subtask_id": subtask.id,
                            "ok": False,
                            "reason": reason,
                            "trace_id": result.trace_id,
                            "attempt": attempt,
                        },
                    )
                )
                return SubtaskOutcome(
                    subtask.id,
                    ok=False,
                    error=OrchestrationErrorCode.TASK_TOKEN_BUDGET_EXCEEDED,
                    reason=reason,
                    trace_id=result.trace_id,
                    attempt=attempt,
                )
            verify = await self._decomposer.verify(subtask, result.reply)
            self._trace(
                task_id,
                "subtask_verified",
                {
                    "subtask_id": subtask.id,
                    "passed": verify.passed,
                    "reason": verify.reason,
                    "attempt": attempt,
                },
            )
            # E63：验收通过**且**执行未失败才算通过（对齐 delegate 正解 `not result.failed`）；
            # 执行失败态（循环未达成 / 异常终止 / 预算耗尽）fail-closed，不因合成回复非空而假成功。
            ok = verify.passed and not result.failed
            reason = verify.reason
            if ok is False and verify.passed:
                reason = "子任务执行未达成目标"
            emit(
                LoopEvent(
                    "subtask_completed",
                    {
                        "task_id": task_id,
                        "subtask_id": subtask.id,
                        "ok": ok,
                        "reason": reason,
                        "trace_id": result.trace_id,
                        "reply": result.reply[:_MAX_EVENT_EXCERPT],
                        "attempt": attempt,
                    },
                )
            )
            if ok:
                self._tracker.record(task_id, subtask.id)
                self._results.setdefault(task_id, {})[subtask.id] = result.reply[:MAX_HANDOFF_CHARS]
                return SubtaskOutcome(
                    subtask.id,
                    ok=True,
                    trace_id=result.trace_id,
                    reply=result.reply[:MAX_HANDOFF_CHARS],
                    attempt=attempt,
                )
            error = (
                OrchestrationErrorCode.SUBTASK_VERIFY_FAILED
                if not verify.passed
                else OrchestrationErrorCode.SUBTASK_EXECUTION_FAILED
            )
            return SubtaskOutcome(
                subtask.id,
                ok=False,
                error=error,
                reason=reason,
                trace_id=result.trace_id,
                attempt=attempt,
            )

    def _replan_input(self, task_id: str, goal: str, plan: Plan, failure: _Failure) -> str:
        """重新拆解输入：原目标 + 已完成摘要 + 失败项与原因（有界）。"""
        completed = [s for s in plan.subtasks if s.id in self._tracker.completed(task_id)]
        lines = [f"原始目标：{goal}"]
        if completed:
            lines.append("已完成子任务（不要重复安排）：")
            lines.extend(f"- {s.id}: {s.goal}" for s in completed)
        if failure.failed:
            lines.append("失败子任务（需重新安排）：")
            lines.extend(f"- {sid}: {failure.reason}" for sid in failure.failed)
        elif failure.code == OrchestrationErrorCode.DEADLOOP_DETECTED:
            lines.append("上一轮未取得进展（疑似死循环），请换一种拆解策略。")
        lines.append("请重新拆解尚未完成的部分；已完成的部分不要重复。")
        return "\n".join(lines)[:MAX_HANDOFF_CHARS]

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

    def _build_handoff(  # noqa: PLR0913 — 交接注入面（会话 / 重试）
        self,
        task_id: str,
        plan: Plan,
        subtask: Subtask,
        *,
        session_id: str,
        attempt: int,
        previous_reason: str,
    ) -> TaskHandoff:
        """构造交接：TaskHandoff 全字段（change 0247 / ADR-0235）。

        ``task`` = 子任务目标（重试时追加有界失败提示）；``context_pack`` = 原目标 +
        依赖的验收通过结果（有界）；``deadline`` 由构造注入的 ``subtask_timeout`` 给出
        （`0` ⇒ 不设限）。
        """
        results = self._results.get(task_id, {})
        by_id = {s.id: s for s in plan.subtasks}
        dependencies = [
            (dep, by_id[dep].goal if dep in by_id else "", results[dep])
            for dep in subtask.depends_on
            if dep in results
        ]
        task = subtask.goal
        if attempt > 1 and previous_reason:
            task = (
                f"{task}\n\n[重试提示] 上一次执行未通过："
                f"{previous_reason[:_MAX_EVENT_EXCERPT]}"
                f"（第 {attempt} 次执行，请针对该原因修正）"
            )
        return TaskHandoff(
            task=task,
            context_pack=build_context_pack(
                plan.goal, dependencies, max_tokens=DEFAULT_CONTEXT_TOKENS
            ),
            acceptance=subtask.acceptance,
            deadline=float(self._subtask_timeout) if self._subtask_timeout > 0 else None,
            priority=subtask.priority,
            session_id=session_id,
        )

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
