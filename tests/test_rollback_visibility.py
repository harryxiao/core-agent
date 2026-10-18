"""失败回滚可见性（change 0268）：整轮回滚 + 遥测 + 观察回灌。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from core.loop import Action, DefaultLoop, LoopContext
from core.observability import TraceEvent, Tracer
from core.plugin_registry import CoeffectResolver
from core.tools import Tool, ToolDef, ToolProvider


def _provider() -> ToolProvider:
    resolver = CoeffectResolver()
    resolver.register("filesystem:write", True)
    return ToolProvider(coeffect_resolver=resolver)


def _write_tool(undone: list[str], *, fail_undo: bool = False) -> Tool:
    def handler(**args: Any) -> dict[str, Any]:
        return {"value": "written"}

    def undo_factory():
        def undo() -> None:
            if fail_undo:
                raise RuntimeError("undo boom")  # noqa: TRY003 — 测试用撤销失败探针
            undone.append("write")

        return undo

    return Tool(
        definition=ToolDef(
            tool_id="tools.write",
            description="write",
            schema={"type": "object"},
            coeffects=["filesystem:write"],
            reversible=True,
        ),
        handler=handler,
        undo=undo_factory,
    )


def _fail_tool() -> Tool:
    def handler(**args: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    return Tool(
        definition=ToolDef(
            tool_id="tools.fail",
            description="fail",
            schema={"type": "object"},
            coeffects=["filesystem:write"],
            reversible=False,
        ),
        handler=handler,
    )


class _CapturingExporter:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def emit(self, events: list[TraceEvent]) -> None:
        self.events.extend(events)


def _run(loop: DefaultLoop) -> None:
    async def _stream() -> None:
        async for _event in loop.astream("任务"):
            pass

    asyncio.run(_stream())


def _tool_observations(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [json.loads(str(m["content"])) for m in messages if m.get("role") == "tool"]


def test_prior_write_rollback_is_visible() -> None:
    undone: list[str] = []
    provider = _provider()
    provider.register(_write_tool(undone))
    provider.register(_fail_tool())
    exporter = _CapturingExporter()
    seen: list[dict[str, Any]] = []

    def planner(ctx: LoopContext) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id="tools.write", args={})
        if ctx.rounds == 1:
            return Action(tool_id="tools.fail", args={})
        seen.extend(ctx.messages)
        return Action(args={"reply": "done"})

    loop = DefaultLoop(
        planner=planner, tools=provider, tracer=Tracer(exporter=exporter), max_rounds=5
    )
    _run(loop)

    assert undone == ["write"]
    observations = _tool_observations(seen)
    assert observations[-1]["rollback"] == {"reverted": 1, "undo_failed": 0}
    rolled_back = [e for e in exporter.events if e.kind == "trace_rolled_back"]
    assert len(rolled_back) == 1
    assert rolled_back[0].payload == {"reverted": 1, "undo_failed": 0}


def test_no_rollback_key_when_no_effects() -> None:
    provider = _provider()
    provider.register(_fail_tool())
    exporter = _CapturingExporter()
    seen: list[dict[str, Any]] = []

    def planner(ctx: LoopContext) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id="tools.fail", args={})
        seen.extend(ctx.messages)
        return Action(args={"reply": "done"})

    loop = DefaultLoop(
        planner=planner, tools=provider, tracer=Tracer(exporter=exporter), max_rounds=5
    )
    _run(loop)

    observations = _tool_observations(seen)
    assert "rollback" not in observations[-1]
    assert [e for e in exporter.events if e.kind == "trace_rolled_back"] == []


def test_undo_failure_is_reported_and_quarantined() -> None:
    undone: list[str] = []
    provider = _provider()
    provider.register(_write_tool(undone, fail_undo=True))
    provider.register(_fail_tool())
    exporter = _CapturingExporter()
    seen: list[dict[str, Any]] = []

    def planner(ctx: LoopContext) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id="tools.write", args={})
        if ctx.rounds == 1:
            return Action(tool_id="tools.fail", args={})
        seen.extend(ctx.messages)
        return Action(args={"reply": "done"})

    loop = DefaultLoop(
        planner=planner, tools=provider, tracer=Tracer(exporter=exporter), max_rounds=5
    )
    _run(loop)

    assert undone == []
    observations = _tool_observations(seen)
    assert observations[-1]["rollback"] == {"reverted": 0, "undo_failed": 1}
    rolled_back = [e for e in exporter.events if e.kind == "trace_rolled_back"]
    assert len(rolled_back) == 1
    assert rolled_back[0].payload == {"reverted": 0, "undo_failed": 1}
    # 撤销失败者留在账目隔离：再次回滚仍报 undo_failed（不自动删除 / 不自动重试成功）。
    assert len(provider.rollback(rolled_back[0].trace_id).undo_failed) == 1
