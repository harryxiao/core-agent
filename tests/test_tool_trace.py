"""工具级 trace 生产方接线（change 0107 / E30）。

loop 是**唯一**同时持有（动作 + 执行结果 + 耗时）的位置 ⇒ 工具调用遥测在 loop 产出；
消费侧 `_to_traces` 的 `tool_use` 通道由此在**生产**有输入（此前只有消费侧就绪）。
trace 封口后事件不再驻留内存 ⇒ 观察点是导出器（`Exporter.emit`），与生产路径一致。
"""

from __future__ import annotations

from core.evolution.worker import EvolutionWorker
from core.loop import Action, DefaultLoop, LoopContext
from core.observability import TraceEvent, Tracer
from core.tools import Tool, ToolDef, ToolProvider

_TOOL_ID = "tools.echo"


class _CapturingExporter:
    """收集封口交付的事件批次（trace 封口是事件的唯一交付点）。"""

    def __init__(self) -> None:
        self.batches: list[list[TraceEvent]] = []

    def emit(self, events: list[TraceEvent]) -> None:
        self.batches.append(list(events))


def _events(exporter: _CapturingExporter) -> list[TraceEvent]:
    return [event for batch in exporter.batches for event in batch]


def _tools() -> ToolProvider:
    provider = ToolProvider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id=_TOOL_ID,
                description="echo",
                schema={"type": "object", "properties": {"text": {"type": "string"}}},
                coeffects=[],
                reversible=True,
            ),
            handler=lambda text: f"echo:{text}",
        )
    )
    return provider


def _tool_then_reply(tool_id: str = _TOOL_ID):
    """首轮调工具、次轮终止回复的 planner（保证有非终止动作）。"""

    def planner(ctx: LoopContext) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id=tool_id, args={"text": "中间结论"})
        return Action(args={"reply": "done"})

    return planner


def _run(*, planner, tracer: Tracer | None = None) -> _CapturingExporter:
    exporter = _CapturingExporter()
    loop = DefaultLoop(
        planner=planner,
        tools=_tools(),
        tracer=tracer if tracer is not None else Tracer(exporter=exporter),
        max_rounds=3,
    )
    loop.run("任务")
    return exporter


def test_tool_action_emits_tool_call_trace() -> None:
    """非终止动作完成后产出 kind="tool_call" 遥测（供给侧接线）。"""
    exporter = _run(planner=_tool_then_reply())
    calls = [event for event in _events(exporter) if event.kind == "tool_call"]

    assert len(calls) == 1, "一个工具动作 → 一条工具调用遥测"
    payload = calls[0].payload
    assert payload["tool"] == _TOOL_ID
    assert payload["args"] == {"text": "中间结论"}
    assert payload["result"]["ok"] is True
    assert isinstance(payload["latency_ms"], float)


def test_failed_tool_action_emits_tool_call_trace_with_failure() -> None:
    """执行失败也产遥测（成败是诊断证据的核心字段），成败写入 result.ok。"""
    exporter = _CapturingExporter()
    loop = DefaultLoop(
        planner=_tool_then_reply(tool_id="tools.missing"),
        tools=_tools(),
        tracer=Tracer(exporter=exporter),
        max_rounds=3,
    )
    loop.run("任务")

    calls = [event for event in _events(exporter) if event.kind == "tool_call"]
    assert [call.payload["tool"] for call in calls] == ["tools.missing"]
    assert calls[0].payload["result"]["ok"] is False, "失败动作不得被写成成功证据"


def test_terminal_action_emits_no_tool_call_trace() -> None:
    """终止动作非工具调用 ⇒ 不产遥测（与 action_completed 同判据）。"""
    exporter = _CapturingExporter()
    loop = DefaultLoop(
        planner=lambda _ctx: Action(args={"reply": "done"}),
        tools=_tools(),
        tracer=Tracer(exporter=exporter),
        max_rounds=3,
    )
    loop.run("任务")

    assert [event.kind for event in _events(exporter) if event.kind == "tool_call"] == []


def test_loop_without_tracer_still_runs() -> None:
    """未注入 tracer ⇒ 不产遥测，且本轮回复与终止语义不变（缺省路径不破）。"""
    loop = DefaultLoop(planner=_tool_then_reply(), tools=_tools(), max_rounds=3)
    result = loop.run("任务")

    assert not result.failed and result.reply == "done"


def test_tool_call_trace_feeds_evolution_tool_channel() -> None:
    """端到端：生产的遥测经 _to_traces 产出按工具 id 归因的业务证据（skill 维度有输入）。"""
    exporter = _run(planner=_tool_then_reply())
    traces = EvolutionWorker._to_traces(_events(exporter))

    tool_traces = [trace for trace in traces if trace.task_type == "tool_use"]
    assert len(tool_traces) == 1, "工具调用通道在生产有产出"
    assert tool_traces[0].plugin_id == _TOOL_ID, "按工具 id 归因（技能级候选的归因对象）"
    assert tool_traces[0].success is True
