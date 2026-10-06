"""子任务运行态实时回流（change 0121 / phase-29 change A：E51）。

覆盖：里程碑事件实时回流 / `reply_delta` 不外发 / 载荷白名单化 / 白名单外类型不外发 /
附加通道不改终态 / `collect_result` 与 `arun` 同语义。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, cast

from core.loop import Action, DefaultLoop, LoopEvent, LoopPlugin, LoopResult, collect_result
from core.orchestration import (
    AgentProfile,
    MultiAgentRouter,
    StateMachine,
    Subtask,
    SubtaskDecomposer,
    TaskScheduler,
)
from core.tools import Tool, ToolDef, ToolProvider

# 内层事件类型 → 允许外发的载荷键（与实现的白名单表同口径；测试**独立**列出以防实现漂移）。
_WHITELIST: dict[str, set[str]] = {
    "action_started": {"round", "tool_id", "args"},
    "action_completed": {"round", "tool_id", "ok", "duration_ms", "output"},
    "step_completed": {"round", "failed"},
}


def _echo_tool() -> Tool:
    return Tool(
        definition=ToolDef(
            tool_id="tools.echo",
            description="echo",
            schema={"type": "object", "properties": {"text": {"type": "string"}}},
            coeffects=[],
            reversible=True,
        ),
        handler=lambda text: f"echo:{text}",
    )


def _scheduler(loop: Any) -> TaskScheduler:
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=cast("LoopPlugin", loop))
    decomposer = SubtaskDecomposer(
        planner=lambda goal: [Subtask(id="s1", goal="t-one", acceptance="")]
    )
    return TaskScheduler(
        decomposer=decomposer,
        router=MultiAgentRouter(agents=[profile]),
        state_machine=StateMachine(),
    )


def _task_events(scheduler: TaskScheduler) -> list[LoopEvent]:
    async def _run() -> list[LoopEvent]:
        return [event async for event in scheduler.astream("task-1", "goal")]

    return asyncio.run(_run())


class _StreamingPlanner:
    """duck-typed 流式 planner：先逐 delta 外发自然语言，末态产出终 Action。"""

    def __init__(self, deltas: list[str], action: Action) -> None:
        self._deltas = deltas
        self._action = action

    async def astream(self, ctx: Any) -> AsyncIterator[str | Action]:
        for delta in self._deltas:
            yield delta
        yield self._action


class _FakeStreamLoop:
    """按给定事件序外发的最小 LoopPlugin 替身（用于构造白名单/未知类型边界）。"""

    def __init__(self, *events: LoopEvent) -> None:
        self._events = list(events)

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        for event in self._events:
            yield event

    async def arun(self, user_input: str, *, session_id: str = "") -> LoopResult:
        return await collect_result(self.astream(user_input, session_id=session_id))


def _finished(reply: str = "ok", trace_id: str = "t1") -> LoopEvent:
    return LoopEvent("loop_finished", LoopResult(reply=reply, trace_id=trace_id))


# ---- 里程碑实时回流 ----


def test_milestone_events_relayed_as_subtask_progress() -> None:
    """子任务经子 Agent 流式执行 ⇒ 里程碑事件依序外发为 `subtask_progress`（附归属与时间戳）。"""
    provider = ToolProvider()
    provider.register(_echo_tool())

    def planner(ctx: Any) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "hi"})
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, tools=provider, max_rounds=5)
    events = _task_events(_scheduler(loop))
    progress = [cast(dict[str, Any], e.payload) for e in events if e.type == "subtask_progress"]

    assert [p["event"] for p in progress] == [
        "action_started",
        "action_completed",
        "step_completed",
        "step_completed",
    ]
    assert all(p["task_id"] == "task-1" for p in progress)
    assert all(p["subtask_id"] == "s1" for p in progress)
    assert all(isinstance(p["ts"], float) for p in progress)
    # 回流发生在子任务完成之前（「实时」而非收尾补发）
    types = [e.type for e in events]
    assert types.index("subtask_progress") < types.index("subtask_completed")


def test_reply_delta_never_relayed() -> None:
    """模型流式原文（`reply_delta`）不外发 —— 既洪泛又暴露未定稿原文。"""
    loop = DefaultLoop(
        planner=_StreamingPlanner(["秘", "密"], Action(args={"reply": "秘密"})), max_rounds=3
    )
    events = _task_events(_scheduler(loop))
    progress = [cast(dict[str, Any], e.payload) for e in events if e.type == "subtask_progress"]

    assert progress, "里程碑仍应回流（reply_delta 排除不影响其余类型）"
    assert "reply_delta" not in {p["event"] for p in progress}
    assert "秘密" not in str(progress)


# ---- 载荷白名单化 ----


def test_payload_is_whitelisted_per_event_type() -> None:
    """载荷按内层类型白名单取键：多带的字段（含疑似凭据）一律不外发。"""
    loop = _FakeStreamLoop(
        LoopEvent(
            "action_started",
            {"round": 1, "tool_id": "t", "args": {"a": 1}, "api_key": "sk-secret"},
        ),
        LoopEvent(
            "action_completed",
            {
                "round": 1,
                "tool_id": "t",
                "ok": True,
                "duration_ms": 3,
                "output": "x",
                "secret": "s",
            },
        ),
        LoopEvent("step_completed", {"round": 1, "failed": False, "extra": 1}),
        _finished(),
    )
    events = _task_events(_scheduler(loop))
    progress = [cast(dict[str, Any], e.payload) for e in events if e.type == "subtask_progress"]

    assert [p["event"] for p in progress] == [
        "action_started",
        "action_completed",
        "step_completed",
    ]
    for item in progress:
        assert set(cast(dict[str, Any], item["data"])) <= _WHITELIST[item["event"]]
    assert "sk-secret" not in str(progress)
    assert '"secret"' not in str(progress)


def test_unknown_event_type_not_relayed() -> None:
    """白名单外的事件类型（含未来新增）不外发。"""
    loop = _FakeStreamLoop(
        LoopEvent("custom_event", {"x": 1}),
        LoopEvent("loop_started", {"trace_id": "t1"}),
        _finished(),
    )
    events = _task_events(_scheduler(loop))

    assert [e.type for e in events if e.type == "subtask_progress"] == []


# ---- 附加通道、终态不变 ----


def test_progress_is_additive_terminal_outcome_unchanged() -> None:
    """有里程碑 / 无里程碑两次运行 ⇒ `SubtaskOutcome` 与推进判据逐字一致。"""
    with_progress = _FakeStreamLoop(
        LoopEvent("action_started", {"round": 1, "tool_id": "t", "args": {}}),
        LoopEvent("step_completed", {"round": 1, "failed": False}),
        _finished(),
    )
    without_progress = _FakeStreamLoop(_finished())

    def _outcome(loop: Any) -> Any:
        events = _task_events(_scheduler(loop))
        assert [e.type for e in events][-1] == "task_finished"
        finished = cast(dict[str, Any], events[-1].payload)
        return cast(list[Any], finished["outcomes"])[0]

    a, b = _outcome(with_progress), _outcome(without_progress)
    assert (a.ok, a.trace_id, a.reply) == (b.ok, b.trace_id, b.reply) == (True, "t1", "ok")


# ---- `collect_result` 与 `arun` 同语义（单一真源守门）----


def test_collect_result_matches_arun_on_success() -> None:
    """`arun` 即 `collect_result·astream` 的薄壳：回复/成败与「拿到 trace_id」逐字一致。"""
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "ok"}))

    async def _run() -> tuple[LoopResult, LoopResult]:
        return await loop.arun("hi"), await collect_result(loop.astream("hi"))

    a, b = asyncio.run(_run())
    assert (a.reply, a.failed) == (b.reply, b.failed) == ("ok", False)
    assert a.trace_id and b.trace_id  # 各自新一轮 ⇒ trace_id 不同，但都取自 loop_started


def test_collect_result_normalizes_loop_failed() -> None:
    """`loop_failed` 归一为 `failed=True` 且回复取 `reason`（与 `arun` 逐字一致）。"""
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "x"}), max_rounds=0)

    async def _run() -> tuple[LoopResult, LoopResult]:
        return await loop.arun("hi"), await collect_result(loop.astream("hi"))

    a, b = asyncio.run(_run())
    assert a.failed is True and b.failed is True
    assert a.reply == b.reply
