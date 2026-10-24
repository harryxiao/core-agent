"""单子任务自跑（甲-2）与计划草案产出（change 0313）。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from core.loop import Action, DefaultLoop, LoopEvent
from core.orchestration import (
    AgentProfile,
    MultiAgentRouter,
    OrchestrationError,
    OrchestrationErrorCode,
    StateMachine,
    Subtask,
    SubtaskDecomposer,
    TaskScheduler,
    TaskState,
)
from core.orchestration.handoff import MAX_HANDOFF_CHARS


class _RecordingLoop(DefaultLoop):
    """按次序回放回复，并记录收到的交接输入 / 会话标识。"""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0
        self.inputs: list[str] = []
        self.sessions: list[str] = []
        super().__init__(planner=self._plan)

    def _plan(self, ctx: Any) -> Action:
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return Action(args={"reply": reply})

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        self.inputs.append(user_input)
        self.sessions.append(session_id)
        async for event in super().astream(user_input, session_id=session_id):
            yield event


class _RecordingRouter(MultiAgentRouter):
    """记录 match 调用；未命中时沿用既有 NO_AGENT_MATCH 语义。"""

    def __init__(self, agents: list[AgentProfile]) -> None:
        super().__init__(agents=agents)
        self.matched: list[str] = []

    def match(self, task: str) -> AgentProfile:
        self.matched.append(task)
        return super().match(task)


class _RecordingTracer:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def record(self, event: Any) -> None:
        self.events.append((getattr(event, "trace_id", ""), getattr(event, "kind", "")))


def _planner(subtasks: list[Subtask]) -> tuple[Any, list[str]]:
    seen: list[str] = []

    def plan(goal: str) -> list[Subtask]:
        seen.append(goal)
        return list(subtasks)

    return plan, seen


def _scheduler(
    *,
    planner: Any,
    router: MultiAgentRouter,
    self_loop: DefaultLoop | None = None,
    tracer: Any = None,
    checkpoint: Any = None,
) -> TaskScheduler:
    return TaskScheduler(
        decomposer=SubtaskDecomposer(planner=planner),
        router=router,
        state_machine=StateMachine(),
        self_loop=self_loop,
        tracer=tracer,
        checkpoint=checkpoint,
    )


def test_self_run_single_subtask_uses_main_loop() -> None:
    main = _RecordingLoop(["done"])
    sub = _RecordingLoop(["sub-done"])
    router = _RecordingRouter([AgentProfile(agent_id="sub", capabilities=["t"], loop=sub)])
    planner, _ = _planner([Subtask(id="1", goal="t-one", acceptance="")])
    scheduler = _scheduler(planner=planner, router=router, self_loop=main)

    outcomes = asyncio.run(scheduler.run("task", "goal", self_run=True))

    assert [o.ok for o in outcomes] == [True]
    assert len(main.inputs) == 1
    assert "t-one" in main.inputs[0]
    assert sub.inputs == []
    assert router.matched == []  # 不经能力路由
    assert scheduler._state_machine.state("task") == TaskState.DONE


def test_self_run_multiple_subtasks_uses_router() -> None:
    main = _RecordingLoop(["main"])
    sub = _RecordingLoop(["sub"])
    router = _RecordingRouter([AgentProfile(agent_id="sub", capabilities=["t"], loop=sub)])
    planner, _ = _planner(
        [
            Subtask(id="1", goal="t-one", acceptance=""),
            Subtask(id="2", goal="t-two", acceptance=""),
        ]
    )
    scheduler = _scheduler(planner=planner, router=router, self_loop=main)

    outcomes = asyncio.run(scheduler.run("task", "goal", self_run=True))

    assert [o.ok for o in outcomes] == [True, True]
    assert main.inputs == []
    assert len(sub.inputs) == 2  # noqa: PLR2004 — 两个子任务各一次
    assert len(router.matched) == 2  # noqa: PLR2004 — 两个子任务各一次


def test_self_run_default_off_keeps_router_path() -> None:
    main = _RecordingLoop(["main"])
    sub = _RecordingLoop(["sub"])
    router = _RecordingRouter([AgentProfile(agent_id="sub", capabilities=["t"], loop=sub)])
    planner, _ = _planner([Subtask(id="1", goal="t-one", acceptance="")])
    scheduler = _scheduler(planner=planner, router=router, self_loop=main)

    asyncio.run(scheduler.run("task", "goal"))  # 未声明自跑

    assert main.inputs == []
    assert len(sub.inputs) == 1


def test_self_run_without_main_loop_falls_back_to_router() -> None:
    sub = _RecordingLoop(["sub"])
    router = _RecordingRouter([AgentProfile(agent_id="sub", capabilities=["t"], loop=sub)])
    planner, _ = _planner([Subtask(id="1", goal="t-one", acceptance="")])
    scheduler = _scheduler(planner=planner, router=router)

    outcomes = asyncio.run(scheduler.run("task", "goal", self_run=True))

    assert [o.ok for o in outcomes] == [True]
    assert len(sub.inputs) == 1


def test_self_run_failure_keeps_retry_and_replan_semantics() -> None:
    main = _RecordingLoop(["", ""])
    router = _RecordingRouter([])  # 自跑生效时永远不会被匹配
    planner, seen = _planner([Subtask(id="1", goal="t-one", acceptance="")])
    scheduler = _scheduler(planner=planner, router=router, self_loop=main)

    with pytest.raises(OrchestrationError) as exc:
        asyncio.run(scheduler.run("task", "goal", self_run=True))

    assert exc.value.code == OrchestrationErrorCode.SUBTASK_VERIFY_FAILED
    assert main.calls == 4  # noqa: PLR2004 — 首发 + 重试 + 重拆后首发 + 重试
    assert len(seen) == 2  # noqa: PLR2004 — 首拆 + 重拆
    assert scheduler._state_machine.state("task") == TaskState.FAILED


def test_self_run_carries_session_id() -> None:
    main = _RecordingLoop(["ok"])
    router = _RecordingRouter([])
    planner, _ = _planner([Subtask(id="1", goal="t-one", acceptance="")])
    scheduler = _scheduler(planner=planner, router=router, self_loop=main)

    asyncio.run(scheduler.run("task", "goal", session_id="s-1", self_run=True))

    assert main.sessions == ["s-1"]


def test_draft_plan_restores_goal_bounds_context_and_has_no_side_effects() -> None:
    tracer = _RecordingTracer()
    checkpoints: list[tuple[str, str]] = []
    sub = _RecordingLoop(["sub"])
    router = _RecordingRouter([AgentProfile(agent_id="sub", capabilities=["t"], loop=sub)])
    planner, seen = _planner(
        [Subtask(id="1", goal="t-one", acceptance=""), Subtask(id="2", goal="t-two", acceptance="")]
    )
    scheduler = _scheduler(
        planner=planner,
        router=router,
        tracer=tracer,
        checkpoint=lambda task_id, outcomes, plan, session_id: checkpoints.append(
            (task_id, session_id)
        ),
    )

    plan = asyncio.run(scheduler.draft_plan("原始目标", context="x" * (MAX_HANDOFF_CHARS + 100)))

    assert plan.goal == "原始目标"
    assert [s.id for s in plan.subtasks] == ["1", "2"]
    assert MAX_HANDOFF_CHARS * "x" in seen[0]
    assert (MAX_HANDOFF_CHARS + 1) * "x" not in seen[0]
    assert tracer.events == []
    assert checkpoints == []
    assert sub.inputs == []  # 草案不执行
    assert router.matched == []


def _echo_planner() -> tuple[Any, list[str]]:
    """拆解器回落形态：单子任务，目标逐字等于送入文本。"""
    seen: list[str] = []

    def plan(goal: str) -> list[Subtask]:
        seen.append(goal)
        return [Subtask(id="1", goal=goal, acceptance="")]

    return plan, seen


def test_draft_plan_normalizes_planner_fallback_goal() -> None:
    """回落计划不得把勘察结论当子任务指令（change 0316 / ui 实测回归）。

    `LLMSubtaskPlanner._fallback` 把**送入拆解的整段文本**用作唯一子任务目标；草案入口须还原
    为原始目标，否则批准后主 Agent 按「无法执行……建议安装插件」这段勘察文字执行。
    """
    planner, seen = _echo_planner()
    scheduler = _scheduler(planner=planner, router=_RecordingRouter([]))

    plan = asyncio.run(scheduler.draft_plan("帮我检索论文", context="勘察结论：未安装插件"))

    assert "【只读勘察结论（供拆解参考）】" in seen[0]  # 上下文确实送入了拆解
    assert plan.goal == "帮我检索论文"
    assert [s.goal for s in plan.subtasks] == ["帮我检索论文"]


def test_draft_plan_keeps_non_fallback_single_subtask_goal() -> None:
    """正常拆解出的单子任务（目标 ≠ 送入文本）逐字保留 —— 归一不误伤。"""
    planner, _ = _planner([Subtask(id="1", goal="检索 arxiv 论文", acceptance="列出 3 篇")])
    scheduler = _scheduler(planner=planner, router=_RecordingRouter([]))

    plan = asyncio.run(scheduler.draft_plan("帮我检索论文", context="勘察结论"))

    assert [s.goal for s in plan.subtasks] == ["检索 arxiv 论文"]
    assert [s.acceptance for s in plan.subtasks] == ["列出 3 篇"]
