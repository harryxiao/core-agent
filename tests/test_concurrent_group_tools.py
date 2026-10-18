"""组内工具并发执行（change 0265）。

只读动作并发 + 写屏障 + 按序提交 + 同步 handler 卸载。时间阈值只判「是否重叠」，
均留足余量（串行上界 vs 并发上界相差约一倍）。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from core.loop import Action, ActionGroup, DefaultLoop, LoopContext
from core.observability import TraceEvent, Tracer
from core.plugin_registry import CoeffectResolver
from core.tools import Tool, ToolDef, ToolProvider

_DELAY = 0.2
_MIN_TICKS = 10  # 20ms 内约 3 tick；200ms 阻塞期间应显著更多


def _provider() -> ToolProvider:
    resolver = CoeffectResolver()
    for coeffect in ("filesystem:read", "filesystem:write"):
        resolver.register(coeffect, True)
    return ToolProvider(coeffect_resolver=resolver)


def _sleep_tool(  # noqa: PLR0913
    tool_id: str,
    coeffects: list[str],
    delay: float,
    log: list[str],
    *,
    label: str = "",
    result_key: str = "value",
    reversible: bool = False,
) -> Tool:
    def handler(**args: Any) -> dict[str, Any]:
        name = str(args.get("text") or label or tool_id)
        log.append(f"start:{name}")
        time.sleep(delay)
        log.append(f"end:{name}")
        return {result_key: name}

    return Tool(
        definition=ToolDef(
            tool_id=tool_id,
            description="sleep",
            schema={"type": "object"},
            coeffects=coeffects,
            reversible=reversible,
        ),
        handler=handler,
    )


def _run(loop: DefaultLoop) -> list[Any]:
    async def _stream() -> list[Any]:
        return [event async for event in loop.astream("任务")]

    return asyncio.run(_stream())


class _CapturingExporter:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def emit(self, events: list[TraceEvent]) -> None:
        self.events.extend(events)


def _two_read_planner(tool_id: str):
    def planner(ctx: LoopContext) -> Action | ActionGroup:
        if ctx.rounds == 0:
            return ActionGroup(
                [
                    Action(tool_id=tool_id, args={"text": "a"}),
                    Action(tool_id=tool_id, args={"text": "b"}),
                ]
            )
        return Action(args={"reply": "done"})

    return planner


def test_read_only_group_actions_run_concurrently() -> None:
    log: list[str] = []
    provider = _provider()
    provider.register(_sleep_tool("tools.read", ["filesystem:read"], _DELAY, log))

    loop = DefaultLoop(planner=_two_read_planner("tools.read"), tools=provider, max_rounds=5)
    started = time.perf_counter()
    _run(loop)
    elapsed = time.perf_counter() - started

    assert sorted(log) == ["end:a", "end:b", "start:a", "start:b"]
    assert log[0].startswith("start:") and log[1].startswith("start:")
    assert elapsed < _DELAY * 1.75, f"只读动作未重叠执行（耗时 {elapsed:.3f}s）"


def test_write_action_is_a_barrier() -> None:
    log: list[str] = []
    provider = _provider()
    provider.register(_sleep_tool("tools.read", ["filesystem:read"], _DELAY, log))
    provider.register(_sleep_tool("tools.write", ["filesystem:write"], 0.0, log, reversible=True))

    def planner(ctx: LoopContext) -> Action | ActionGroup:
        if ctx.rounds == 0:
            return ActionGroup(
                [
                    Action(tool_id="tools.read", args={"text": "read"}),
                    Action(tool_id="tools.write", args={"text": "write"}),
                ]
            )
        return Action(args={"reply": "done"})

    _run(DefaultLoop(planner=planner, tools=provider, max_rounds=5))

    assert log.index("end:read") < log.index("start:write")


def test_concurrent_results_commit_in_index_order() -> None:
    log: list[str] = []
    provider = _provider()
    provider.register(_sleep_tool("tools.read", ["filesystem:read"], 0.0, log))

    # 同一工具按参数区分耗时：a 慢、b 快 ⇒ 完成顺序反转，提交仍须按 a、b。
    def handler(**args: Any) -> dict[str, Any]:
        name = str(args.get("text"))
        log.append(f"start:{name}")
        time.sleep(0.25 if name == "a" else 0.05)
        log.append(f"end:{name}")
        return {"value": name}

    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.read",
                description="sleep",
                schema={"type": "object"},
                coeffects=["filesystem:read"],
                reversible=False,
            ),
            handler=handler,
        )
    )
    loop = DefaultLoop(planner=_two_read_planner("tools.read"), tools=provider, max_rounds=5)
    events = _run(loop)

    assert log.index("end:b") < log.index("end:a")  # 确已乱序完成
    completed = [e for e in events if e.type == "action_completed"]
    assert [e.payload["round"] for e in completed] == [0, 1]
    assert "'a'" in completed[0].payload["output"]
    assert "'b'" in completed[1].payload["output"]


def test_concurrent_reads_can_be_disabled() -> None:
    log: list[str] = []
    provider = _provider()
    provider.register(_sleep_tool("tools.read", ["filesystem:read"], _DELAY, log))

    loop = DefaultLoop(
        planner=_two_read_planner("tools.read"),
        tools=provider,
        max_rounds=5,
        concurrent_reads=False,
    )
    started = time.perf_counter()
    _run(loop)
    elapsed = time.perf_counter() - started

    assert elapsed >= _DELAY * 1.75, f"开关关闭后仍并发（耗时 {elapsed:.3f}s）"
    assert log == ["start:a", "end:a", "start:b", "end:b"]


def test_duplicate_key_in_group_is_not_prefetched() -> None:
    log: list[str] = []
    provider = _provider()
    provider.register(_sleep_tool("tools.read", ["filesystem:read"], 0.0, log))
    exporter = _CapturingExporter()

    def planner(ctx: LoopContext) -> Action | ActionGroup:
        if ctx.rounds == 0:
            action = Action(tool_id="tools.read", args={"text": "x"})
            return ActionGroup([action, action])
        return Action(args={"reply": "done"})

    _run(
        DefaultLoop(
            planner=planner,
            tools=provider,
            tracer=Tracer(exporter=exporter),
            max_rounds=5,
        )
    )

    assert log == ["start:x", "end:x"]
    deduped = [e for e in exporter.events if e.kind == "action_deduplicated"]
    assert [e.payload["scope"] for e in deduped] == ["batch"]


def test_concurrent_batch_does_not_exceed_max_rounds() -> None:
    log: list[str] = []
    provider = _provider()
    provider.register(_sleep_tool("tools.read", ["filesystem:read"], 0.05, log))

    def planner(ctx: LoopContext) -> Action | ActionGroup:
        if ctx.rounds == 0:
            return ActionGroup(
                [Action(tool_id="tools.read", args={"text": n}) for n in ("a", "b", "c")]
            )
        return Action(args={"reply": "done"})

    _run(DefaultLoop(planner=planner, tools=provider, max_rounds=2))

    assert [line for line in log if line.startswith("start:")] == ["start:a", "start:b"]


# ---- ToolProvider：同步 handler 卸载 ----


def _sync_tool(delay: float, *, coeffects: list[str] | None = None) -> Tool:
    def handler(**args: Any) -> dict[str, Any]:
        time.sleep(delay)
        return {"ok": True}

    return Tool(
        definition=ToolDef(
            tool_id="tools.sync",
            description="sync",
            schema={"type": "object"},
            coeffects=coeffects if coeffects is not None else [],
            reversible=False,
        ),
        handler=handler,
    )


def test_sync_handler_does_not_block_event_loop() -> None:
    provider = _provider()
    provider.register(_sync_tool(0.2))
    ticks = [0]

    async def scenario() -> int:
        stop = asyncio.Event()

        async def ticker() -> None:
            while not stop.is_set():
                ticks[0] += 1
                await asyncio.sleep(0.01)

        task = asyncio.create_task(ticker())
        await asyncio.sleep(0.02)
        await provider.ainvoke("tools.sync", {}, trace_id="t")
        stop.set()
        await task
        return ticks[0]

    count = asyncio.run(scenario())
    assert count >= _MIN_TICKS, f"事件循环被同步 handler 阻塞（tick={count}）"


def test_sync_handlers_run_concurrently_via_ainvoke() -> None:
    provider = _provider()
    provider.register(_sync_tool(_DELAY))

    async def scenario() -> float:
        started = time.perf_counter()
        await asyncio.gather(
            provider.ainvoke("tools.sync", {"n": 1}, trace_id="t"),
            provider.ainvoke("tools.sync", {"n": 2}, trace_id="t"),
        )
        return time.perf_counter() - started

    elapsed = asyncio.run(scenario())
    assert elapsed < _DELAY * 1.75, f"同步 handler 未并发（耗时 {elapsed:.3f}s）"
