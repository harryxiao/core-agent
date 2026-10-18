"""TaskHandoff 统一执行框架（change 0247 / ADR-0235 / 台账 E182）。

覆盖：context_pack 有界 / render 空上下文逐字不变 / deadline 超时归一 SUBTASK_TIMEOUT /
router 全字段与 fallback 解析 / scheduler 构造并消费 TaskHandoff 全字段。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from core.loop import LoopEvent, LoopResult
from core.orchestration import (
    AgentProfile,
    DecomposeResult,
    MultiAgentRouter,
    OrchestrationError,
    OrchestrationErrorCode,
    Plan,
    StateMachine,
    Subtask,
    SubtaskDecomposer,
    TaskHandoff,
    TaskScheduler,
    TaskState,
    VerifyResult,
)
from core.orchestration.handoff import (
    MAX_HANDOFF_CHARS,
    build_context_pack,
    render_handoff,
    run_handoff,
    stream_handoff,
)
from core.tokens import estimate_tokens


class RecordingLoop:
    """记录 prompt / session，可选挂起以触发超时。"""

    def __init__(self, reply: str = "ok", *, hang: bool = False) -> None:
        self.reply = reply
        self.hang = hang
        self.prompts: list[str] = []
        self.sessions: list[str] = []
        self.cancelled = False

    async def _events(self, prompt: str, session_id: str) -> AsyncIterator[LoopEvent]:
        self.prompts.append(prompt)
        self.sessions.append(session_id)
        yield LoopEvent("loop_started", {"trace_id": "t1"})
        if self.hang:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        yield LoopEvent("loop_finished", LoopResult(reply=self.reply, trace_id="t1"))

    def astream(self, prompt: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        return self._events(prompt, session_id)

    async def arun(self, prompt: str, *, session_id: str = "") -> LoopResult:
        self.prompts.append(prompt)
        self.sessions.append(session_id)
        return LoopResult(reply=self.reply, trace_id="t1")


def _agent(loop: RecordingLoop, *, agent_id: str = "worker") -> AgentProfile:
    return AgentProfile(agent_id=agent_id, capabilities=["任务", "task"], loop=loop)


# ---- 上下文包 ----


def test_build_context_pack_stops_when_budget_exhausted() -> None:
    """预算耗尽 ⇒ 停止装入后续依赖（有界，不无界拼接）。"""
    dependencies = [("a", "dep-a", "x" * 5000), ("b", "dep-b", "y" * 5000)]
    pack = build_context_pack("goal", dependencies, max_tokens=50)
    assert pack["goal"] == "goal"
    assert len(pack["dependencies"]) == 1
    assert len(pack["dependencies"][0]["result"]) < 5000  # noqa: PLR2004 — 已被预算截断


def test_build_context_pack_caps_single_field() -> None:
    """单条字段另受字符上界约束（预算充足也不得超 MAX_HANDOFF_CHARS）。"""
    pack = build_context_pack("goal", [("a", "dep-a", "x" * 5000)], max_tokens=100_000)
    assert len(pack["dependencies"][0]["result"]) == MAX_HANDOFF_CHARS


def test_build_context_pack_keeps_short_dependencies_verbatim() -> None:
    pack = build_context_pack("goal", [("a", "dep-a", "result-a")], max_tokens=1000)
    assert pack["dependencies"] == [{"id": "a", "goal": "dep-a", "result": "result-a"}]


# ---- 渲染 ----


def test_render_handoff_empty_context_is_byte_identical() -> None:
    """beast / pet 空上下文 ⇒ 逐字返回 task（既有行为不变）。"""
    assert render_handoff(TaskHandoff(task="do it")) == "do it"


def test_render_handoff_includes_context_and_acceptance() -> None:
    handoff = TaskHandoff(
        task="write code",
        context_pack=build_context_pack("top goal", [("a", "dep-a", "result-a")], max_tokens=1000),
        acceptance="must compile",
    )
    text = render_handoff(handoff)
    assert text.startswith("write code")
    assert "top goal" in text
    assert "result-a" in text
    assert "must compile" in text


# ---- 执行与超时 ----


def test_stream_handoff_passes_task_and_session() -> None:
    loop = RecordingLoop()

    async def _run() -> list[LoopEvent]:
        return [e async for e in stream_handoff(loop, TaskHandoff(task="q", session_id="s1"))]

    events = asyncio.run(_run())
    assert [e.type for e in events] == ["loop_started", "loop_finished"]
    assert loop.prompts == ["q"]
    assert loop.sessions == ["s1"]


def test_stream_handoff_timeout_cancels_and_raises() -> None:
    loop = RecordingLoop(hang=True)

    async def _run() -> None:
        async for _ in stream_handoff(loop, TaskHandoff(task="q"), deadline=0.01):
            pass

    with pytest.raises(OrchestrationError) as exc:
        asyncio.run(_run())
    assert exc.value.code == OrchestrationErrorCode.SUBTASK_TIMEOUT
    assert loop.cancelled is True


def test_run_handoff_uses_arun_and_forwards_session() -> None:
    loop = RecordingLoop()
    result = asyncio.run(run_handoff(loop, TaskHandoff(task="q", session_id="s2")))
    assert result.reply == "ok"
    assert loop.prompts == ["q"]
    assert loop.sessions == ["s2"]


# ---- Router ----


def test_router_handoff_consumes_all_fields() -> None:
    loop = RecordingLoop()
    router = MultiAgentRouter([_agent(loop)])
    handoff = TaskHandoff(
        task="q",
        context_pack=build_context_pack("top", [("a", "dep-a", "res")], max_tokens=1000),
        acceptance="acc",
        deadline=5,
        priority=2,
        session_id="s3",
    )
    asyncio.run(router.handoff("worker", handoff))
    prompt = loop.prompts[0]
    assert "top" in prompt and "res" in prompt and "acc" in prompt
    assert loop.sessions == ["s3"]


def test_router_handoff_stream_resolves_fallback_profile() -> None:
    """match() 返回未登记的 fallback 画像 ⇒ 按 id 仍可解析执行。"""
    loop = RecordingLoop()
    fallback = AgentProfile(agent_id="general", capabilities=["default"], loop=loop)
    router = MultiAgentRouter([], fallback=fallback)
    profile = router.match("anything")

    async def _run() -> None:
        async for _ in router.handoff_stream(profile.agent_id, TaskHandoff(task="q")):
            pass

    asyncio.run(_run())
    assert loop.prompts == ["q"]


# ---- Scheduler 集成 ----


def _scheduler(loop: RecordingLoop, *, subtask_timeout: float = 0) -> TaskScheduler:
    planner = lambda goal: [  # noqa: E731 — 测试桩
        Subtask(id="a", goal="first 任务", acceptance=""),
        Subtask(id="b", goal="second 任务", acceptance="must pass", depends_on=["a"], priority=2),
    ]
    return TaskScheduler(
        decomposer=SubtaskDecomposer(planner=planner),
        router=MultiAgentRouter([_agent(loop)]),
        state_machine=StateMachine(),
        subtask_timeout=subtask_timeout,
    )


def test_scheduler_consumes_task_handoff_all_fields() -> None:
    loop = RecordingLoop(reply="done")
    scheduler = _scheduler(loop, subtask_timeout=30)
    outcomes = asyncio.run(scheduler.run("task", "top goal", session_id="sess-9"))
    assert [o.ok for o in outcomes] == [True, True]
    second_prompt = loop.prompts[1]
    assert "top goal" in second_prompt  # context_pack.goal
    assert "done" in second_prompt  # 前置结果
    assert "must pass" in second_prompt  # acceptance
    assert loop.sessions == ["sess-9", "sess-9"]


def test_scheduler_build_handoff_carries_deadline_and_priority() -> None:
    scheduler = _scheduler(RecordingLoop(), subtask_timeout=30)
    plan = asyncio.run(scheduler._decomposer.decompose("top"))  # noqa: SLF001 — 接线断言
    handoff = scheduler._build_handoff(  # noqa: SLF001 — 接线断言
        "task", plan, plan.subtasks[1], session_id="s", attempt=1, previous_reason=""
    )
    assert handoff.deadline == 30  # noqa: PLR2004 — 即构造注入值
    assert handoff.priority == 2  # noqa: PLR2004 — 即子任务优先级
    assert handoff.acceptance == "must pass"
    assert handoff.session_id == "s"


# ---- 任务级成功标准进入交接（change 0291） ----


def _handoff_for(acceptance: str, criteria: list[str]) -> TaskHandoff:
    scheduler = _scheduler(RecordingLoop())
    plan = Plan(
        subtasks=[Subtask(id="b", goal="second 任务", acceptance=acceptance)],
        goal="top",
        success_criteria=criteria,
    )
    return scheduler._build_handoff(  # noqa: SLF001 — 接线断言
        "task", plan, plan.subtasks[0], session_id="s", attempt=1, previous_reason=""
    )


def test_handoff_acceptance_appends_task_criteria() -> None:
    handoff = _handoff_for("must pass", ["整体标准 A", "整体标准 B"])
    assert handoff.acceptance.startswith("must pass")
    assert "任务级成功标准（整体必须满足）：" in handoff.acceptance
    assert "- 整体标准 A" in handoff.acceptance
    assert "- 整体标准 B" in handoff.acceptance


def test_handoff_acceptance_byte_identical_without_criteria() -> None:
    assert _handoff_for("must pass", []).acceptance == "must pass"
    assert _handoff_for("", []).acceptance == ""


def test_handoff_acceptance_bounded_with_long_criteria() -> None:
    acceptance = "A" * 1900
    criteria = ["标准 " + "B" * 300 for _ in range(5)]
    handoff = _handoff_for(acceptance, criteria)
    assert len(handoff.acceptance) <= MAX_HANDOFF_CHARS
    assert "任务级成功标准（整体必须满足）：" in handoff.acceptance
    assert handoff.acceptance.startswith("A")


def test_first_attempt_prompt_contains_task_criteria() -> None:
    """执行者首轮即可见任务级标准（不必等重拆）。"""
    loop = RecordingLoop(reply="done")
    planner = lambda goal: DecomposeResult(  # noqa: E731 — 测试桩
        subtasks=[Subtask(id="a", goal="first 任务", acceptance="")],
        success_criteria=["整体标准 A"],
    )
    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(planner=planner),
        router=MultiAgentRouter([_agent(loop)]),
        state_machine=StateMachine(),
        success_checker=lambda *_: VerifyResult(passed=True, reason="ok"),
    )
    asyncio.run(scheduler.run("task", "top goal"))
    assert "任务级成功标准（整体必须满足）：" in loop.prompts[0]
    assert "整体标准 A" in loop.prompts[0]


def test_subtask_verifier_receives_original_acceptance() -> None:
    """任务级标准只进执行输入，子任务验收仍按子任务自身 acceptance。"""
    seen: list[str] = []

    def verifier(subtask: Subtask, result: object) -> VerifyResult:
        seen.append(subtask.acceptance)
        return VerifyResult(passed=True, reason="ok")

    loop = RecordingLoop(reply="done")
    planner = lambda goal: DecomposeResult(  # noqa: E731 — 测试桩
        subtasks=[Subtask(id="a", goal="first 任务", acceptance="must pass")],
        success_criteria=["整体标准 A"],
    )
    scheduler = TaskScheduler(
        decomposer=SubtaskDecomposer(planner=planner, verifier=verifier),
        router=MultiAgentRouter([_agent(loop)]),
        state_machine=StateMachine(),
        success_checker=lambda *_: VerifyResult(passed=True, reason="ok"),
    )
    asyncio.run(scheduler.run("task", "top goal"))
    assert seen == ["must pass"]


def test_scheduler_timeout_fails_after_recovery_budget() -> None:
    """超时归一 SUBTASK_TIMEOUT；重试 + 重拆各 1 次后终态沿用该码。"""
    scheduler = _scheduler(RecordingLoop(hang=True), subtask_timeout=0.01)
    with pytest.raises(OrchestrationError) as exc:
        asyncio.run(scheduler.run("task", "top goal"))
    assert exc.value.code == OrchestrationErrorCode.SUBTASK_TIMEOUT
    assert scheduler._state_machine.state("task") is TaskState.FAILED  # noqa: SLF001


def test_context_pack_fits_rendered_budget() -> None:
    """渲染后的交接文本不随依赖数量无界增长（回归护栏）。"""
    dependencies = [(f"d{i}", "goal", "x" * 5000) for i in range(20)]
    pack = build_context_pack("goal", dependencies, max_tokens=200)
    rendered = render_handoff(TaskHandoff(task="t", context_pack=pack))
    assert estimate_tokens(rendered) < 400  # noqa: PLR2004 — 远小于 20×5000 字符
    assert isinstance(pack, dict)
