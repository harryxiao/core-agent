"""原生并行工具调用 / 重复写抑制（change 0257 / ADR-0248 / 台账 E194）。

会话复盘中「并行 tool_calls 只执行首个」导致模型重复写：planner 静默丢弃其余调用，
模型据此误判失败并在后续轮次重发。本组用例锁三层口径：planner 全量映射、
loop 按序执行、完全相同的调用只执行一次（批内 + 轮内紧邻）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from core.llm_provider import LLMChunk, LLMResponse, TokenUsage, ToolCall
from core.loop import Action, ActionGroup, DefaultLoop, LoopContext
from core.loop.planner import LLMPlanner
from core.observability import TraceEvent, Tracer
from core.plugin_registry import CoeffectResolver
from core.tools import Tool, ToolDef, ToolProvider


def _provider() -> ToolProvider:
    resolver = CoeffectResolver()
    resolver.register("filesystem:write", True)
    return ToolProvider(coeffect_resolver=resolver)


class _NativeLLM:
    def __init__(self, tool_calls: list[ToolCall]) -> None:
        self._tool_calls = tool_calls

    async def acompletion(self, request: object) -> LLMResponse:
        return LLMResponse(
            content="",
            usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
            finish_reason="tool_calls",
            provider="fake",
            model="test-model",
            tool_calls=self._tool_calls,
        )


class _StreamingNativeLLM:
    def __init__(self, chunks: list[LLMChunk]) -> None:
        self._chunks = chunks

    async def astream(self, request: object):
        for chunk in self._chunks:
            yield chunk


def _call(tool_id: str, index: int, **args: Any) -> ToolCall:
    return ToolCall(tool_id=tool_id, arguments=json.dumps(args), index=index)


def test_planner_maps_all_native_tool_calls() -> None:
    """非流式多调用 ⇒ ActionGroup 按 index 全量映射（不再取首个）。"""
    planner = LLMPlanner(
        _NativeLLM(
            [
                _call("tools.echo", 0, text="a"),
                _call("tools.write", 1, path="p", content="x"),
            ]
        )
    )
    result = asyncio.run(planner(LoopContext(messages=["hi"])))
    assert isinstance(result, ActionGroup)
    assert [(action.tool_id, action.args) for action in result.actions] == [
        ("tools.echo", {"text": "a"}),
        ("tools.write", {"path": "p", "content": "x"}),
    ]


def test_planner_single_native_tool_call_stays_action() -> None:
    """单调用仍返回 Action（既有协议与断言逐字不变）。"""
    planner = LLMPlanner(_NativeLLM([_call("tools.echo", 0, text="a")]))
    assert asyncio.run(planner(LoopContext(messages=["hi"]))) == Action(
        tool_id="tools.echo", args={"text": "a"}
    )


def test_planner_astream_maps_all_native_tool_calls() -> None:
    """流式多 index 片段 ⇒ ActionGroup 顺序稳定。"""
    planner = LLMPlanner(
        _StreamingNativeLLM(
            [
                LLMChunk(
                    content="",
                    tool_calls=[
                        ToolCall(tool_id="tools.echo", arguments='{"text": "a"}', index=0),
                        ToolCall(
                            tool_id="tools.write",
                            arguments='{"path": "p", "content": "x"}',
                            index=1,
                        ),
                    ],
                )
            ]
        )
    )

    async def _collect() -> list[Any]:
        return [item async for item in planner.astream(LoopContext(messages=["hi"]))]

    items = asyncio.run(_collect())
    assert len(items) == 1 and isinstance(items[0], ActionGroup)
    assert [action.tool_id for action in items[0].actions] == ["tools.echo", "tools.write"]


def test_planner_batch_with_invalid_arguments_is_terminal_failure() -> None:
    """批次中任一参数非法 ⇒ 单个失败终止动作，不产出部分动作组。"""
    planner = LLMPlanner(
        _NativeLLM(
            [
                _call("tools.echo", 0, text="a"),
                ToolCall(tool_id="tools.write", arguments="{oops", index=1),
            ]
        )
    )
    result = asyncio.run(planner(LoopContext(messages=["hi"])))
    assert isinstance(result, Action)
    assert result.is_terminal
    assert "LLM_PLAN_PARSE_FAILED" in result.args["reply"]


class _CapturingExporter:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def emit(self, events: list[TraceEvent]) -> None:
        self.events.extend(events)


def _recording_tool(tool_id: str, calls: list[dict[str, Any]]) -> Tool:
    def handler(**args: Any) -> dict[str, Any]:
        calls.append(args)
        return {"ok": True}

    return Tool(
        definition=ToolDef(
            tool_id=tool_id,
            description="record",
            schema={"type": "object"},
            coeffects=["filesystem:write"],
            reversible=True,
        ),
        handler=handler,
    )


def _run(loop: DefaultLoop) -> list[Any]:
    async def _stream() -> list[Any]:
        return [event async for event in loop.astream("任务")]

    return asyncio.run(_stream())


def test_loop_executes_every_action_in_group() -> None:
    """动作组两个调用 ⇒ 各执行一次、两轮动作事件、按序推进。"""
    calls: list[dict[str, Any]] = []
    provider = _provider()
    provider.register(_recording_tool("tools.echo", calls))

    def planner(ctx: LoopContext) -> Action | ActionGroup:
        if ctx.rounds == 0:
            return ActionGroup(
                [
                    Action(tool_id="tools.echo", args={"text": "a"}),
                    Action(tool_id="tools.echo", args={"text": "b"}),
                ]
            )
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, tools=provider, max_rounds=5)
    events = _run(loop)

    assert calls == [{"text": "a"}, {"text": "b"}]
    started = [e for e in events if e.type == "action_started"]
    assert [e.payload["round"] for e in started] == [0, 1]
    assert events[-1].type == "loop_finished"


def test_duplicate_calls_in_one_batch_execute_once() -> None:
    """批内完全相同 ⇒ 处理器只调用一次，另一次留 action_deduplicated(scope=batch)。"""
    calls: list[dict[str, Any]] = []
    provider = _provider()
    provider.register(_recording_tool("tools.echo", calls))
    exporter = _CapturingExporter()

    def planner(ctx: LoopContext) -> Action | ActionGroup:
        if ctx.rounds == 0:
            return ActionGroup(
                [
                    Action(tool_id="tools.echo", args={"text": "x"}),
                    Action(tool_id="tools.echo", args={"text": "x"}),
                ]
            )
        return Action(args={"reply": "done"})

    loop = DefaultLoop(
        planner=planner,
        tools=provider,
        tracer=Tracer(exporter=exporter),
        max_rounds=5,
    )
    _run(loop)

    assert calls == [{"text": "x"}]
    deduped = [e for e in exporter.events if e.kind == "action_deduplicated"]
    assert len(deduped) == 1
    assert deduped[0].payload["scope"] == "batch"
    assert deduped[0].payload["tool_id"] == "tools.echo"
    assert "text" not in deduped[0].payload


def test_consecutive_identical_write_is_deduplicated() -> None:
    """轮内紧邻重复写（覆盖模式）⇒ 只执行一次，留 action_deduplicated(scope=turn)。"""
    calls: list[dict[str, Any]] = []
    provider = _provider()
    provider.register(_recording_tool("tools.file_write", calls))
    exporter = _CapturingExporter()
    write = Action(tool_id="tools.file_write", args={"path": "p", "content": "x"})

    def planner(ctx: LoopContext) -> Action:
        if ctx.rounds < 2:  # noqa: PLR2004 — 轮次阈值
            return write
        return Action(args={"reply": "done"})

    loop = DefaultLoop(
        planner=planner,
        tools=provider,
        tracer=Tracer(exporter=exporter),
        max_rounds=5,
    )
    _run(loop)

    assert calls == [{"path": "p", "content": "x"}]
    deduped = [e for e in exporter.events if e.kind == "action_deduplicated"]
    assert len(deduped) == 1
    assert deduped[0].payload["scope"] == "turn"


def test_identical_write_after_other_action_is_not_deduplicated() -> None:
    """中间隔着其他动作 ⇒ 相同写不再抑制（避免误杀合法重写）。"""
    calls: list[dict[str, Any]] = []
    provider = _provider()
    provider.register(_recording_tool("tools.file_write", calls))
    provider.register(_recording_tool("tools.echo", []))
    write = Action(tool_id="tools.file_write", args={"path": "p", "content": "x"})

    def planner(ctx: LoopContext) -> Action:
        if ctx.rounds == 0:
            return write
        if ctx.rounds == 1:
            return Action(tool_id="tools.echo", args={"text": "z"})
        if ctx.rounds == 2:  # noqa: PLR2004 — 轮次阈值
            return write
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, tools=provider, max_rounds=6)
    _run(loop)

    assert calls == [{"path": "p", "content": "x"}, {"path": "p", "content": "x"}]
