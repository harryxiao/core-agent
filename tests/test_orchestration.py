"""orchestration 单元测试（对齐 §13 契约 + M3 验收锚点）。

覆盖：状态机合法/非法转移与断点续跑 / 子任务拆解拓扑序波次划分与成环检测 /
多 Agent 能力匹配交接与无匹配处理 / 波次并行扇出（真并发 + 资源上限）/
优先级调度 / fan-in 校验推进 / 进度追踪死循环哨兵。
"""

from __future__ import annotations

import asyncio

import pytest

from core.loop import Action, DefaultLoop, LoopResult
from core.orchestration import (
    AgentProfile,
    MultiAgentRouter,
    OrchestrationError,
    OrchestrationErrorCode,
    ProgressTracker,
    StateMachine,
    Subtask,
    SubtaskDecomposer,
    TaskHandoff,
    TaskScheduler,
    TaskState,
)

# ---- 状态机 ----


def test_valid_transition_chain() -> None:
    sm = StateMachine()
    for to in (TaskState.PLANNING, TaskState.EXECUTING, TaskState.VERIFYING, TaskState.DONE):
        sm.transition("t", to)
    assert sm.state("t") == TaskState.DONE


def test_invalid_transition_rejected() -> None:
    sm = StateMachine()
    with pytest.raises(OrchestrationError) as exc:
        sm.transition("t", TaskState.EXECUTING)  # CREATED → EXECUTING 非法
    assert exc.value.code == OrchestrationErrorCode.INVALID_TRANSITION


def test_active_state_can_fail() -> None:
    sm = StateMachine()
    sm.transition("t", TaskState.PLANNING)
    sm.transition("t", TaskState.EXECUTING)
    sm.transition("t", TaskState.FAILED)  # 熔断 / 人工终止
    assert sm.state("t") == TaskState.FAILED


def test_unknown_task_defaults_created() -> None:
    assert StateMachine().state("missing") == TaskState.CREATED


# ---- 子任务拆解 ----


def test_decompose_default_single_subtask() -> None:
    plan = SubtaskDecomposer().decompose("do thing")
    assert [s.id for s in plan.subtasks] == ["1"]
    assert plan.order == ["1"]
    assert plan.waves == [["1"]]


def test_decompose_topological_order_and_waves() -> None:
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [
            Subtask(id="a", goal="", acceptance=""),
            Subtask(id="b", goal="", acceptance=""),
            Subtask(id="c", goal="", acceptance="", depends_on=["a", "b"]),
            Subtask(id="d", goal="", acceptance="", depends_on=["c"]),
        ]
    )
    plan = decomposer.decompose("goal")
    assert plan.order == ["a", "b", "c", "d"]
    assert plan.waves == [["a", "b"], ["c"], ["d"]]


def test_decompose_cycle_detected() -> None:
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [
            Subtask(id="a", goal="", acceptance="", depends_on=["b"]),
            Subtask(id="b", goal="", acceptance="", depends_on=["a"]),
        ]
    )
    with pytest.raises(OrchestrationError) as exc:
        decomposer.decompose("goal")
    assert exc.value.code == OrchestrationErrorCode.DEADLOOP_DETECTED


def test_verify_empty_result_fails() -> None:
    decomposer = SubtaskDecomposer()
    subtask = Subtask(id="1", goal="", acceptance="")
    assert decomposer.verify(subtask, "").passed is False


def test_verify_nonempty_passes() -> None:
    decomposer = SubtaskDecomposer()
    subtask = Subtask(id="1", goal="", acceptance="")
    assert decomposer.verify(subtask, "ok").passed is True


# ---- 多 Agent 路由 ----


def _loop(reply: str) -> DefaultLoop:
    return DefaultLoop(planner=lambda ctx: Action(args={"reply": reply}))


def test_match_by_capability() -> None:
    coder = AgentProfile(agent_id="coder", capabilities=["code"], loop=_loop("ok"))
    analyst = AgentProfile(agent_id="analyst", capabilities=["analysis"], loop=_loop("ok"))
    router = MultiAgentRouter(agents=[coder, analyst])
    assert router.match("fix the code bug") is coder


def test_match_fallback_when_no_hit() -> None:
    fallback = AgentProfile(agent_id="fb", capabilities=["general"], loop=_loop("ok"))
    router = MultiAgentRouter(
        agents=[AgentProfile(agent_id="coder", capabilities=["code"], loop=_loop("ok"))],
        fallback=fallback,
    )
    assert router.match("write a poem") is fallback


def test_match_none_when_no_hit_no_fallback() -> None:
    router = MultiAgentRouter(
        agents=[AgentProfile(agent_id="coder", capabilities=["code"], loop=_loop("ok"))]
    )
    assert router.match("write a poem") is None


def test_handoff_returns_trace_id() -> None:
    router = MultiAgentRouter(
        agents=[AgentProfile(agent_id="a", capabilities=["code"], loop=_loop("done"))]
    )
    trace_id = router.handoff("a", TaskHandoff(task="fix bug"))
    assert trace_id


def test_handoff_unknown_agent_raises() -> None:
    router = MultiAgentRouter()
    with pytest.raises(OrchestrationError) as exc:
        router.handoff("nope", TaskHandoff(task="x"))
    assert exc.value.code == OrchestrationErrorCode.NO_AGENT_MATCH


# ---- 进度追踪 ----


def test_progress_tracker_detects_stall() -> None:
    tracker = ProgressTracker(stall_limit=3)
    assert tracker.detect_stall("t") is False
    assert tracker.detect_stall("t") is False
    assert tracker.detect_stall("t") is True  # 连续三次签名一致 → 死循环


def test_progress_tracker_no_stall_when_progressing() -> None:
    tracker = ProgressTracker(stall_limit=3)
    tracker.detect_stall("t")
    tracker.record("t", "s1")
    tracker.detect_stall("t")
    tracker.record("t", "s2")
    assert tracker.detect_stall("t") is False


# ---- 调度器 ----


class _ConcurrencyTracker:
    """记录执行顺序与并发峰值（asyncio 单线程，无需加锁）。"""

    def __init__(self) -> None:
        self.order: list[str] = []
        self.active = 0
        self.peak = 0

    def enter(self, name: str) -> None:
        self.order.append(name)
        self.active += 1
        self.peak = max(self.peak, self.active)

    def exit(self) -> None:
        self.active -= 1


class _TrackingLoop(DefaultLoop):
    """带并发窗口与顺序记录的测试循环。"""

    def __init__(self, reply: str, tracker: _ConcurrencyTracker) -> None:
        super().__init__(planner=lambda ctx: Action(args={"reply": reply}))
        self._tracker = tracker

    async def arun(self, user_input: str) -> LoopResult:
        self._tracker.enter(user_input)
        await asyncio.sleep(0.01)
        result = await super().arun(user_input)
        self._tracker.exit()
        return result


def test_run_completes_and_marks_done() -> None:
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=_loop("ok"))
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [
            Subtask(id="a1", goal="t-one", acceptance=""),
            Subtask(id="a2", goal="t-two", acceptance=""),
        ]
    )
    router = MultiAgentRouter(agents=[profile])
    sm = StateMachine()
    tracker = ProgressTracker()
    scheduler = TaskScheduler(
        decomposer=decomposer, router=router, state_machine=sm, tracker=tracker
    )
    outcomes = asyncio.run(scheduler.run("task", "goal"))
    assert [o.subtask_id for o in outcomes] == ["a1", "a2"]
    assert all(o.ok for o in outcomes)
    assert sm.state("task") == TaskState.DONE
    assert tracker.completed("task") == {"a1", "a2"}


def test_run_fanout_bounded_concurrency() -> None:
    n_subtasks = 6
    concurrency = 2
    tracker = _ConcurrencyTracker()
    loop = _TrackingLoop("ok", tracker)
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=loop)
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [
            Subtask(id=str(i), goal=f"t-{i}", acceptance="") for i in range(n_subtasks)
        ]
    )
    router = MultiAgentRouter(agents=[profile])
    sm = StateMachine()
    scheduler = TaskScheduler(
        decomposer=decomposer, router=router, state_machine=sm, max_concurrency=concurrency
    )
    outcomes = asyncio.run(scheduler.run("task", "goal"))
    assert len(outcomes) == n_subtasks
    assert all(o.ok for o in outcomes)
    assert tracker.peak == concurrency
    assert sm.state("task") == TaskState.DONE


def test_run_priority_order() -> None:
    tracker = _ConcurrencyTracker()
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=_TrackingLoop("ok", tracker))
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [
            Subtask(id="low", goal="t-low", acceptance="", priority=0),
            Subtask(id="high", goal="t-high", acceptance="", priority=10),
            Subtask(id="mid", goal="t-mid", acceptance="", priority=5),
        ]
    )
    router = MultiAgentRouter(agents=[profile])
    sm = StateMachine()
    scheduler = TaskScheduler(
        decomposer=decomposer, router=router, state_machine=sm, max_concurrency=1
    )
    asyncio.run(scheduler.run("task", "goal"))
    assert tracker.order == ["t-high", "t-mid", "t-low"]


def test_run_verify_failure_recovers() -> None:
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=_loop(""))
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [Subtask(id="1", goal="t-one", acceptance="")]
    )
    router = MultiAgentRouter(agents=[profile])
    sm = StateMachine()
    scheduler = TaskScheduler(decomposer=decomposer, router=router, state_machine=sm)
    with pytest.raises(OrchestrationError) as exc:
        asyncio.run(scheduler.run("task", "goal"))
    assert exc.value.code == OrchestrationErrorCode.SUBTASK_VERIFY_FAILED
    assert sm.state("task") == TaskState.RECOVERING


def test_suspend_resume_cancel() -> None:
    sm = StateMachine()
    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(), router=MultiAgentRouter(), state_machine=sm
    )
    sm.transition("t", TaskState.PLANNING)
    sm.transition("t", TaskState.EXECUTING)
    scheduler.suspend("t")
    assert sm.state("t") == TaskState.SUSPENDED
    scheduler.resume("t")
    assert sm.state("t") == TaskState.EXECUTING
    scheduler.cancel("t")
    assert sm.state("t") == TaskState.FAILED


def test_scheduler_rejects_invalid_concurrency() -> None:
    with pytest.raises(OrchestrationError) as exc:
        TaskScheduler(
            decomposer=SubtaskDecomposer(),
            router=MultiAgentRouter(),
            state_machine=StateMachine(),
            max_concurrency=0,
        )
    assert exc.value.code == OrchestrationErrorCode.WAVE_FANOUT_LIMIT
