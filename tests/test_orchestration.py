"""orchestration 单元测试（对齐 §13 契约 + M3 验收锚点）。

覆盖：状态机合法/非法转移与断点续跑 / 子任务拆解拓扑序波次划分与成环检测 /
多 Agent 能力匹配交接与无匹配处理 / 波次并行扇出（真并发 + 资源上限）/
优先级调度 / fan-in 校验推进 / 进度追踪死循环哨兵。
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any, cast

import pytest

from core.llm_provider import LLMError
from core.loop import Action, DefaultLoop, LoopEvent, LoopResult
from core.orchestration import (
    AgentProfile,
    LLMSubtaskPlanner,
    LLMVerifier,
    MultiAgentRouter,
    OrchestrationError,
    OrchestrationErrorCode,
    Plan,
    ProgressTracker,
    StateMachine,
    Subtask,
    SubtaskDecomposer,
    TaskHandoff,
    TaskScheduler,
    TaskState,
    VerifyResult,
    plan_from_dict,
    plan_to_dict,
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
    plan = asyncio.run(SubtaskDecomposer().decompose("do thing"))
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
    plan = asyncio.run(decomposer.decompose("goal"))
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
        asyncio.run(decomposer.decompose("goal"))
    assert exc.value.code == OrchestrationErrorCode.DEADLOOP_DETECTED


def test_verify_empty_result_fails() -> None:
    decomposer = SubtaskDecomposer()
    subtask = Subtask(id="1", goal="", acceptance="")
    assert asyncio.run(decomposer.verify(subtask, "")).passed is False


def test_verify_nonempty_passes() -> None:
    decomposer = SubtaskDecomposer()
    subtask = Subtask(id="1", goal="", acceptance="")
    assert asyncio.run(decomposer.verify(subtask, "ok")).passed is True


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


def test_match_raises_when_no_hit_no_fallback() -> None:
    router = MultiAgentRouter(
        agents=[AgentProfile(agent_id="coder", capabilities=["code"], loop=_loop("ok"))]
    )
    with pytest.raises(OrchestrationError) as exc:
        router.match("write a poem")
    assert exc.value.code == OrchestrationErrorCode.NO_AGENT_MATCH


def test_handoff_returns_loop_result() -> None:
    router = MultiAgentRouter(
        agents=[AgentProfile(agent_id="a", capabilities=["code"], loop=_loop("done"))]
    )
    result = asyncio.run(router.handoff("a", TaskHandoff(task="fix bug")))
    assert result.trace_id
    assert result.reply == "done"
    assert result.failed is False


def test_handoff_unknown_agent_raises() -> None:
    router = MultiAgentRouter()
    with pytest.raises(OrchestrationError) as exc:
        asyncio.run(router.handoff("nope", TaskHandoff(task="x")))
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
    """带并发窗口与顺序记录的测试循环（编排层经流式入口执行子任务）。"""

    def __init__(self, reply: str, tracker: _ConcurrencyTracker) -> None:
        super().__init__(planner=lambda ctx: Action(args={"reply": reply}))
        self._tracker = tracker

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        self._tracker.enter(user_input)
        await asyncio.sleep(0.01)
        self._tracker.exit()
        async for event in super().astream(user_input, session_id=session_id):
            yield event


class _FixedReplyLoop(DefaultLoop):
    """固定回复并记录收到的子任务输入（依赖结果交接断言）。"""

    def __init__(self, reply: str) -> None:
        super().__init__(planner=lambda ctx: Action(args={"reply": reply}))
        self.inputs: list[str] = []

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        self.inputs.append(user_input)
        async for event in super().astream(user_input, session_id=session_id):
            yield event


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
    # 交接 prompt 追加原始目标（change 0247），执行次序按首行判定
    assert [item.split("\n\n")[0] for item in tracker.order] == ["t-high", "t-mid", "t-low"]


class _ScriptedLoop(DefaultLoop):
    """按调用次序回放回复；记录收到的子任务输入（重试/重拆断言）。"""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0
        self.inputs: list[str] = []
        super().__init__(planner=self._plan)

    def _plan(self, ctx: Any) -> Action:
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return Action(args={"reply": reply})

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        self.inputs.append(user_input)
        async for event in super().astream(user_input, session_id=session_id):
            yield event


class _RaisingLoop(DefaultLoop):
    """执行即抛异常（异常归一断言）。"""

    def __init__(self) -> None:
        super().__init__(planner=lambda ctx: Action(args={"reply": "ok"}))

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        raise RuntimeError("boom")
        yield  # pragma: no cover — 使函数成为异步生成器


class _ScriptedPlanner:
    """按调用次序回放计划；记录每次收到的拆解输入。"""

    def __init__(self, plans: list[list[Subtask]]) -> None:
        self._plans = plans
        self.calls: list[str] = []

    def __call__(self, goal: str) -> list[Subtask]:
        self.calls.append(goal)
        return self._plans[min(len(self.calls) - 1, len(self._plans) - 1)]


def test_run_verify_failure_retries_then_replans_then_fails() -> None:
    """首次失败 → 重试 1 次 → 重拆 1 次；预算耗尽落 FAILED（不再悬置 RECOVERING）。"""
    loop = _ScriptedLoop([""])
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=loop)
    planner = _ScriptedPlanner([[Subtask(id="1", goal="t-one", acceptance="")]])
    sm = StateMachine()
    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(planner=planner),
        router=MultiAgentRouter(agents=[profile]),
        state_machine=sm,
    )
    with pytest.raises(OrchestrationError) as exc:
        asyncio.run(scheduler.run("task", "goal"))
    assert exc.value.code == OrchestrationErrorCode.SUBTASK_VERIFY_FAILED
    assert sm.state("task") == TaskState.FAILED
    assert len(planner.calls) == 2  # noqa: PLR2004 — 首拆 + 重拆各一次
    assert loop.calls == 4  # noqa: PLR2004 — 首计划 2 次（首发 + 重试）+ 重拆计划 2 次


def test_run_retry_succeeds_without_replan() -> None:
    loop = _ScriptedLoop(["", "ok"])
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=loop)
    planner = _ScriptedPlanner([[Subtask(id="1", goal="t-one", acceptance="")]])
    sm = StateMachine()
    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(planner=planner),
        router=MultiAgentRouter(agents=[profile]),
        state_machine=sm,
    )
    events = _collect(scheduler, "task", "goal")
    types = [e.type for e in events]
    assert sm.state("task") == TaskState.DONE
    assert len(planner.calls) == 1
    assert types.count("task_retrying") == 1
    assert "task_replanning" not in types
    started = [cast(dict[str, Any], e.payload) for e in events if e.type == "subtask_started"]
    assert [p["attempt"] for p in started] == [1, 2]
    assert cast(dict[str, Any], events[1].payload)["replan"] == 0


def test_run_replan_after_retry_exhausted() -> None:
    loop = _ScriptedLoop(["", "", "ok"])
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=loop)
    planner = _ScriptedPlanner(
        [
            [Subtask(id="1", goal="t-one", acceptance="")],
            [Subtask(id="2", goal="t-two", acceptance="")],
        ]
    )
    sm = StateMachine()
    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(planner=planner),
        router=MultiAgentRouter(agents=[profile]),
        state_machine=sm,
    )
    events = _collect(scheduler, "task", "goal")
    types = [e.type for e in events]
    assert sm.state("task") == TaskState.DONE
    assert types.count("task_replanning") == 1
    ready = [cast(dict[str, Any], e.payload) for e in events if e.type == "plan_ready"]
    assert [p["replan"] for p in ready] == [0, 1]
    assert loop.inputs[-1].startswith("t-two")


def test_run_replan_clears_old_completed_and_results() -> None:
    """重拆后的新 DAG 复用 id 时不得被旧完成集误跳过。"""
    loop = _ScriptedLoop(["ok", "", "", "ok"])
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=loop)
    planner = _ScriptedPlanner(
        [
            [
                Subtask(id="A", goal="t-a", acceptance=""),
                Subtask(id="B", goal="t-b", acceptance=""),
            ],
            [Subtask(id="A", goal="t-new", acceptance="")],
        ]
    )
    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(planner=planner),
        router=MultiAgentRouter(agents=[profile]),
        state_machine=StateMachine(),
    )
    asyncio.run(scheduler.run("task", "goal"))
    assert any(item.startswith("t-new") for item in loop.inputs)


def test_run_execution_exception_normalized() -> None:
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=_RaisingLoop())
    planner = _ScriptedPlanner([[Subtask(id="1", goal="t-one", acceptance="")]])
    sm = StateMachine()
    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(planner=planner),
        router=MultiAgentRouter(agents=[profile]),
        state_machine=sm,
    )
    with pytest.raises(OrchestrationError) as exc:  # 不是裸 RuntimeError
        asyncio.run(scheduler.run("task", "goal"))
    assert exc.value.code == OrchestrationErrorCode.SUBTASK_EXECUTION_FAILED
    assert sm.state("task") == TaskState.FAILED


def test_run_empty_plan_fails_instead_of_done() -> None:
    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(planner=lambda goal: []),
        router=MultiAgentRouter(),
        state_machine=StateMachine(),
    )
    with pytest.raises(OrchestrationError) as exc:
        asyncio.run(scheduler.run("task", "goal"))
    assert exc.value.code == OrchestrationErrorCode.SUBTASK_VERIFY_FAILED


def test_run_success_criteria_unmet_recovers_then_fails() -> None:
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=_loop("ok"))
    planner = _ScriptedPlanner([[Subtask(id="1", goal="t-one", acceptance="")]])
    router = MultiAgentRouter(agents=[profile])
    sm = StateMachine()
    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(planner=planner),
        router=router,
        state_machine=sm,
        success_checker=lambda _: False,
    )
    with pytest.raises(OrchestrationError) as exc:
        asyncio.run(scheduler.run("task", "goal", success_criteria=["c1"]))
    assert exc.value.code == OrchestrationErrorCode.PROGRESS_NOT_MET
    assert sm.state("task") == TaskState.FAILED
    assert len(planner.calls) == 2  # noqa: PLR2004 — 未达标触发一次重拆


def test_run_empty_success_criteria_done() -> None:
    # 空标准走向后兼容分支：即便 checker 恒 False 也直接 DONE，不触发 PROGRESS_NOT_MET
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=_loop("ok"))
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [Subtask(id="1", goal="t-one", acceptance="")]
    )
    router = MultiAgentRouter(agents=[profile])
    sm = StateMachine()
    scheduler = TaskScheduler(
        decomposer=decomposer,
        router=router,
        state_machine=sm,
        success_checker=lambda _: False,
    )
    outcomes = asyncio.run(scheduler.run("task", "goal"))
    assert all(o.ok for o in outcomes)
    assert sm.state("task") == TaskState.DONE


def test_run_criteria_without_checker_fails_fast() -> None:
    # 配置错误：给了 success_criteria 但未注入 success_checker → FAILED（fail-fast），而非静默通过
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=_loop("ok"))
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [Subtask(id="1", goal="t-one", acceptance="")]
    )
    router = MultiAgentRouter(agents=[profile])
    sm = StateMachine()
    scheduler = TaskScheduler(decomposer=decomposer, router=router, state_machine=sm)
    with pytest.raises(OrchestrationError) as exc:
        asyncio.run(scheduler.run("task", "goal", success_criteria=["c1"]))
    assert exc.value.code == OrchestrationErrorCode.MISSING_SUCCESS_CHECKER
    assert sm.state("task") == TaskState.FAILED


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


# ---- LLM 拆解 / 验收适配器 ----


class _FakeLLM:
    """acompletion 桩：固定 content 或抛错；记录调用次数。"""

    def __init__(self, content: str | list[str] = "", error: Exception | None = None) -> None:
        self.contents = [content] if isinstance(content, str) else list(content)
        self.error = error
        self.calls = 0

    async def acompletion(self, request: object) -> object:
        self.calls += 1
        if self.error is not None:
            raise self.error
        # 逐次回放；耗尽后重复末项（重试场景末项即最终输出）
        idx = min(self.calls - 1, len(self.contents) - 1)
        return SimpleNamespace(content=self.contents[idx])


def test_llm_planner_produces_dag() -> None:
    dag = json.dumps(
        {
            "subtasks": [
                {"id": "1", "goal": "抓取页面", "acceptance": "正文非空", "depends_on": []},
                {"id": "2", "goal": "汇总写文件", "acceptance": "文件存在", "depends_on": ["1"]},
                {"id": "bad", "goal": "", "acceptance": "", "depends_on": []},  # 缺 goal 剔除
            ]
        }
    )
    llm = _FakeLLM(content=f"```json\n{dag}\n```")  # 围栏包裹也能解析
    subtasks = asyncio.run(LLMSubtaskPlanner(llm)("复合目标"))
    assert [(s.id, s.depends_on) for s in subtasks] == [("1", []), ("2", ["1"])]
    assert subtasks[0].acceptance == "正文非空"


def test_llm_planner_fallback_on_error_or_garbage() -> None:
    errored = asyncio.run(LLMSubtaskPlanner(_FakeLLM(error=LLMError("boom")))("目标"))
    assert [s.id for s in errored] == ["1"] and errored[0].goal == "目标"
    garbage = asyncio.run(LLMSubtaskPlanner(_FakeLLM(content="无法拆解"))("目标"))
    assert [s.id for s in garbage] == ["1"] and garbage[0].goal == "目标"


def test_llm_verifier_judges_acceptance() -> None:
    ok = _FakeLLM(content='{"passed": true, "reason": "正文非空"}')
    verdict = asyncio.run(LLMVerifier(ok)(Subtask(id="1", goal="g", acceptance="正文非空"), "正文"))
    assert (verdict.passed, verdict.reason) == (True, "正文非空")
    bad = _FakeLLM(content='{"passed": false, "reason": "缺少输出"}')
    verdict = asyncio.run(LLMVerifier(bad)(Subtask(id="1", goal="g", acceptance="x"), ""))
    assert (verdict.passed, verdict.reason) == (False, "缺少输出")


_VERIFY_RETRIES_TOTAL = 2  # 判定调用总次数：首发 + 单次重试


def test_llm_verifier_normalizes_string_bool_and_retries() -> None:
    """判定字段 "true" 字符串归一；不可解析输出重试一次后才 fail-closed。"""
    subtask = Subtask(id="1", goal="g", acceptance="标准")
    flaky = _FakeLLM(["不是 JSON", '{"passed": "true", "reason": "达标"}'])
    verdict = asyncio.run(LLMVerifier(flaky)(subtask, "结果"))
    assert verdict.passed is True
    assert verdict.reason == "达标"
    assert flaky.calls == _VERIFY_RETRIES_TOTAL  # 首次不可解析 → 重试一次

    hopeless = _FakeLLM(["垃圾", "还是垃圾"])
    verdict = asyncio.run(LLMVerifier(hopeless)(subtask, "结果"))
    assert verdict.passed is False
    assert "fail-closed" in verdict.reason
    assert hopeless.calls == _VERIFY_RETRIES_TOTAL  # 重试仍失败 → fail-closed 不放行


def test_llm_verifier_fail_closed() -> None:
    subtask = Subtask(id="1", goal="g", acceptance="a")
    boom = asyncio.run(LLMVerifier(_FakeLLM(error=LLMError("down")))(subtask, "r"))
    assert boom.passed is False and "fail-closed" in boom.reason
    garbage = asyncio.run(LLMVerifier(_FakeLLM(content="看不懂"))(subtask, "r"))
    assert garbage.passed is False


def test_verify_gate_routes_by_acceptance() -> None:
    llm = _FakeLLM(content='{"passed": true, "reason": "ok"}')
    decomposer = SubtaskDecomposer(verifier=LLMVerifier(llm))
    offline = asyncio.run(decomposer.verify(Subtask(id="1", goal="g", acceptance=""), "ok"))
    assert offline.passed is True and llm.calls == 0  # 无验收标准不调模型
    gated = asyncio.run(decomposer.verify(Subtask(id="1", goal="g", acceptance="标准"), "ok"))
    assert gated.passed is True and llm.calls == 1


def test_plan_dict_roundtrip() -> None:
    plan = Plan(
        subtasks=[
            Subtask(id="1", goal="g", acceptance="a", depends_on=[], priority=3),
            Subtask(id="2", goal="h", acceptance="", depends_on=["1"]),
        ],
        goal="G",
        order=["1", "2"],
        success_criteria=["c"],
        waves=[["1"], ["2"]],
        replans=1,
    )
    assert plan_from_dict(plan_to_dict(plan)) == plan
    legacy = plan_to_dict(plan)
    legacy.pop("replans")
    assert plan_from_dict(legacy).replans == 0  # 旧检查点缺键回落 0


# ---- 调度器事件流 / 断点续跑 / 审计 ----


class _Recorder:
    """tracer 桩：收集 trace 事件。"""

    def __init__(self) -> None:
        self.events: list[SimpleNamespace] = []

    def record(self, event: SimpleNamespace) -> None:
        self.events.append(event)


def _collect(scheduler: TaskScheduler, task_id: str, goal: str, **kwargs: Any) -> list[LoopEvent]:
    async def _drive() -> list[LoopEvent]:
        return [event async for event in scheduler.astream(task_id, goal, **kwargs)]

    return asyncio.run(_drive())


def test_scheduler_astream_emits_progress_events() -> None:
    executed = _ConcurrencyTracker()
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [
            Subtask(id="1", goal="t-one", acceptance=""),
            Subtask(id="2", goal="t-two", acceptance="", depends_on=["1"]),
        ]
    )
    recorder = _Recorder()
    scheduler = TaskScheduler(
        decomposer=decomposer,
        router=MultiAgentRouter(
            [AgentProfile(agent_id="a", capabilities=["t"], loop=_TrackingLoop("ok", executed))]
        ),
        state_machine=StateMachine(),
        checkpoint=lambda task_id, outcomes, plan, session_id: None,
        tracer=recorder,
    )
    events = _collect(scheduler, "task", "goal")
    types = [e.type for e in events]
    # 子任务运行态回流（`subtask_progress`）是**附加**事件 ⇒ 任务帧序列按非回流事件断言
    assert [t for t in types if t != "subtask_progress"] == [
        "task_started",
        "plan_ready",
        "wave_started",
        "subtask_started",
        "subtask_completed",
        "task_checkpoint",
        "wave_started",
        "subtask_started",
        "subtask_completed",
        "task_checkpoint",
        "task_finished",
    ]
    # 运行态与任务帧**同流**，且回流发生在该子任务收拢之前（实时而非收尾补发）
    assert "subtask_progress" in types
    assert types.index("subtask_progress") < types.index("subtask_completed")
    plan_payload = cast(dict[str, Any], events[1].payload)
    assert [s["id"] for s in plan_payload["subtasks"]] == ["1", "2"]
    finished = cast(dict[str, Any], events[-1].payload)
    assert [o.ok for o in finished["outcomes"]] == [True, True]
    kinds = {e.kind for e in recorder.events}  # 审计：关键节点写 trace
    assert {"plan_ready", "subtask_verified", "task_checkpoint", "task_finished"} <= kinds


def test_scheduler_checkpoint_callbacks_receive_session_id() -> None:
    """检查点/终态回调收到发起会话标识（change 0190：CheckpointFn/DoneFn 第 4 参）。"""
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [Subtask(id="1", goal="t-one", acceptance="")]
    )
    seen: list[tuple[str, str]] = []

    def checkpoint(task_id, outcomes, plan, session_id):
        seen.append(("checkpoint", session_id))

    def on_done(task_id, outcomes, plan, session_id):
        seen.append(("done", session_id))

    scheduler = TaskScheduler(
        decomposer=decomposer,
        router=MultiAgentRouter(
            [AgentProfile(agent_id="a", capabilities=["t"], loop=_FixedReplyLoop("ok"))]
        ),
        state_machine=StateMachine(),
        checkpoint=checkpoint,
        on_done=on_done,
    )

    outcomes = asyncio.run(scheduler.run("task-s", "goal", session_id="sess-A"))

    assert [o.ok for o in outcomes] == [True]
    # 波次检查点与终态检查点同口径：均携带发起会话（非占位值）
    assert seen == [("checkpoint", "sess-A"), ("done", "sess-A")]


def test_scheduler_checkpoint_callbacks_default_session_empty() -> None:
    """未携带会话 ⇒ 回调收到空串（未归属照实记录，不写占位值）。"""
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [Subtask(id="1", goal="t-one", acceptance="")]
    )
    seen: list[tuple[str, str]] = []

    scheduler = TaskScheduler(
        decomposer=decomposer,
        router=MultiAgentRouter(
            [AgentProfile(agent_id="a", capabilities=["t"], loop=_FixedReplyLoop("ok"))]
        ),
        state_machine=StateMachine(),
        checkpoint=lambda task_id, outcomes, plan, session_id: seen.append(session_id),
    )

    outcomes = asyncio.run(scheduler.run("task-s", "goal"))

    assert [o.ok for o in outcomes] == [True]
    assert seen == [""]


def test_scheduler_done_callback_runs_off_event_loop() -> None:
    """完成回调卸载到工作线程（change 0196：收尾回路不阻塞事件循环）。

    红：变更前 `self._on_done(...)` 同步跑在事件循环（主线程）上 ⇒ ident 等于主线程 ident。
    """
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [Subtask(id="1", goal="t-one", acceptance="")]
    )
    seen: list[int] = []

    def on_done(task_id, outcomes, plan, session_id):
        seen.append(threading.get_ident())

    scheduler = TaskScheduler(
        decomposer=decomposer,
        router=MultiAgentRouter(
            [AgentProfile(agent_id="a", capabilities=["t"], loop=_FixedReplyLoop("ok"))]
        ),
        state_machine=StateMachine(),
        on_done=on_done,
    )

    outcomes = asyncio.run(scheduler.run("task-t", "goal"))

    assert [o.ok for o in outcomes] == [True]
    assert len(seen) == 1, "完成回调仍按 DONE 后一次调用"
    assert seen[0] != threading.main_thread().ident, "完成回调应在工作线程执行，而非事件循环线程"


def test_scheduler_done_callback_does_not_block_event_loop() -> None:
    """回调内阻塞不冻结事件循环（change 0196）。

    结构：回调在**工作线程**上等待某事件，该事件由**事件循环上的**协程释放 —— 若回调同步
    跑在事件循环上，循环被冻结、释放协程永不推进 ⇒ 回调超时（红）。
    """
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [Subtask(id="1", goal="t-one", acceptance="")]
    )
    entered = threading.Event()
    release = threading.Event()
    timed_out: list[bool] = []

    def on_done(task_id, outcomes, plan, session_id):
        entered.set()
        timed_out.append(not release.wait(timeout=2.0))

    scheduler = TaskScheduler(
        decomposer=decomposer,
        router=MultiAgentRouter(
            [AgentProfile(agent_id="a", capabilities=["t"], loop=_FixedReplyLoop("ok"))]
        ),
        state_machine=StateMachine(),
        on_done=on_done,
    )

    async def _drive() -> None:
        async def releaser() -> None:
            for _ in range(100_000):
                if entered.is_set():
                    release.set()
                    return
                await asyncio.sleep(0)

        worker = asyncio.create_task(releaser())
        async for _ in scheduler.astream("task-b", "goal"):
            pass
        await worker

    asyncio.run(_drive())

    assert timed_out == [False], "回调阻塞不应冻结事件循环（卸载后事件循环仍可推进）"


def test_scheduler_astream_failure_visible() -> None:
    decomposer = SubtaskDecomposer(planner=lambda goal: [Subtask(id="1", goal="t", acceptance="")])
    scheduler = TaskScheduler(
        decomposer=decomposer,
        router=MultiAgentRouter([AgentProfile(agent_id="a", capabilities=["t"], loop=_loop(""))]),
        state_machine=StateMachine(),
    )
    events = _collect(scheduler, "task", "goal")
    assert events[-1].type == "task_failed"
    payload = cast(dict[str, Any], events[-1].payload)
    assert payload["code"] == OrchestrationErrorCode.SUBTASK_VERIFY_FAILED
    assert payload["failed"] == ["1"]
    with pytest.raises(OrchestrationError):  # run() 同路径还原抛错语义
        asyncio.run(scheduler.run("task-2", "goal"))


def test_scheduler_resume_skips_completed() -> None:
    executed = _ConcurrencyTracker()
    plan = asyncio.run(
        SubtaskDecomposer(
            planner=lambda goal: [
                Subtask(id="1", goal="t-one", acceptance=""),
                Subtask(id="2", goal="t-two", acceptance=""),
            ]
        ).decompose("goal")
    )
    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(),
        router=MultiAgentRouter(
            [AgentProfile(agent_id="a", capabilities=["t"], loop=_TrackingLoop("ok", executed))]
        ),
        state_machine=StateMachine(),
    )
    events = _collect(scheduler, "task", "goal", plan=plan, completed={"1"})
    # 已完成子任务不重复执行（交接 prompt 追加原始目标，按首行判定）
    assert [item.split("\n\n")[0] for item in executed.order] == ["t-two"]
    skipped = [
        e
        for e in events
        if e.type == "subtask_completed" and cast(dict[str, Any], e.payload).get("skipped")
    ]
    assert [cast(dict[str, Any], e.payload)["subtask_id"] for e in skipped] == ["1"]
    assert events[-1].type == "task_finished"


def test_scheduler_passes_dependency_results() -> None:
    """依赖子任务执行时注入前置子任务的验收通过结果（结果驱动后继）。"""
    loop = _FixedReplyLoop("答案：一叶知秋")
    plan = asyncio.run(
        SubtaskDecomposer(
            planner=lambda goal: [
                Subtask(id="1", goal="t-one", acceptance=""),
                Subtask(id="2", goal="t-two", acceptance="", depends_on=["1"]),
            ]
        ).decompose("goal")
    )
    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(),
        router=MultiAgentRouter([AgentProfile(agent_id="a", capabilities=["t"], loop=loop)]),
        state_machine=StateMachine(),
    )

    _collect(scheduler, "task", "goal", plan=plan)

    assert loop.inputs[0].startswith("t-one")  # 无依赖子任务原样执行
    assert "一叶知秋" in loop.inputs[1]  # 前置结果注入后继输入
    assert "前置子任务结果" in loop.inputs[1]


def test_scheduler_resume_rebuilds_dependency_results() -> None:
    """续跑注入 results 时，依赖上下文自检查点重建（不重跑上游也有结果）。"""
    loop = _FixedReplyLoop("新结果")
    plan = asyncio.run(
        SubtaskDecomposer(
            planner=lambda goal: [
                Subtask(id="1", goal="t-one", acceptance=""),
                Subtask(id="2", goal="t-two", acceptance="", depends_on=["1"]),
            ]
        ).decompose("goal")
    )
    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(),
        router=MultiAgentRouter([AgentProfile(agent_id="a", capabilities=["t"], loop=loop)]),
        state_machine=StateMachine(),
    )

    _collect(scheduler, "task", "goal", plan=plan, completed={"1"}, results={"1": "上游答复"})

    assert loop.inputs == ["t-two\n\n[原始目标] goal\n\n[前置子任务结果]\n- 1: 上游答复"]


# ---- 子任务失败态传播（E63：假成功收口） ----


class _FailedReplyLoop(DefaultLoop):
    """产出非空回复但终态标记失败（模拟循环未达成 / 异常终止 / 预算耗尽）。"""

    def __init__(self, reply: str) -> None:
        super().__init__(planner=lambda ctx: Action(args={"reply": "unused"}))

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        yield LoopEvent("loop_started", {"trace_id": "t-failed"})
        yield LoopEvent(
            "loop_finished", LoopResult(reply="非空合成回复", trace_id="t-failed", failed=True)
        )


def test_failed_execution_without_acceptance_does_not_pass() -> None:
    # 无验收标准 ⇒ 离线判定「回复非空即通过」，但执行失败态必须 fail-closed（否则假成功）
    decomposer = SubtaskDecomposer(planner=lambda goal: [Subtask(id="1", goal="t", acceptance="")])
    sm = StateMachine()
    tracker = ProgressTracker()
    scheduler = TaskScheduler(
        decomposer=decomposer,
        router=MultiAgentRouter(
            [AgentProfile(agent_id="a", capabilities=["t"], loop=_FailedReplyLoop("x"))]
        ),
        state_machine=sm,
        tracker=tracker,
    )
    events = _collect(scheduler, "task", "goal")
    completed = [e for e in events if e.type == "subtask_completed"]
    assert completed and cast(dict[str, Any], completed[0].payload)["ok"] is False
    assert events[-1].type == "task_failed"
    assert tracker.completed("task") == set()
    # 执行失败态进入恢复回路（change 0246）：重试后仍失败 ⇒ 预算耗尽落终态
    assert any(e.type == "task_retrying" for e in events)
    assert sm.state("task") == TaskState.FAILED


def test_failed_execution_with_acceptance_fails_closed() -> None:
    # 验收门本会判通过，但执行失败态仍须 fail-closed
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [Subtask(id="1", goal="t", acceptance="标准")],
        verifier=lambda subtask, result: VerifyResult(passed=True, reason="验收通过"),
    )
    scheduler = TaskScheduler(
        decomposer=decomposer,
        router=MultiAgentRouter(
            [AgentProfile(agent_id="a", capabilities=["t"], loop=_FailedReplyLoop("x"))]
        ),
        state_machine=StateMachine(),
    )
    events = _collect(scheduler, "task", "goal")
    completed = [e for e in events if e.type == "subtask_completed"]
    assert completed and cast(dict[str, Any], completed[0].payload)["ok"] is False
    assert events[-1].type == "task_failed"


def test_successful_execution_still_passes() -> None:
    # 回归：执行成功路径逐字不变（ok=True 且记录完成）
    decomposer = SubtaskDecomposer(planner=lambda goal: [Subtask(id="1", goal="t", acceptance="")])
    sm = StateMachine()
    tracker = ProgressTracker()
    scheduler = TaskScheduler(
        decomposer=decomposer,
        router=MultiAgentRouter([AgentProfile(agent_id="a", capabilities=["t"], loop=_loop("ok"))]),
        state_machine=sm,
        tracker=tracker,
    )
    events = _collect(scheduler, "task", "goal")
    completed = [e for e in events if e.type == "subtask_completed"]
    assert completed and cast(dict[str, Any], completed[0].payload)["ok"] is True
    assert events[-1].type == "task_finished"
    assert tracker.completed("task") == {"1"}
    assert sm.state("task") == TaskState.DONE
