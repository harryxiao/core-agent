"""维护节拍与压实的成本遥测（change 0253 / ADR-0243 / 台账 E189）。

压实/抽取是进程内最重的同步段（摘要器、关键事实抽取器都是模型调用），但此前只有失败留痕，
没有耗时与步骤归因 ⇒ 无法判断「迟到」由哪一步造成。本组用例锁结构化成本事件的口径：
一次节拍/一次压实各一条事件，payload 含总耗时与分步耗时；失败步骤带 `step` 归因且不中断其余步骤。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from core.context import Compaction, Compactor
from core.loop import Action, DefaultLoop, LoopContext
from core.memory import MemoryStore
from core.observability import TraceEvent, Tracer
from core.tools import Tool, ToolDef, ToolProvider


def _maintenance(tracer: Tracer, trace_id: str = "t") -> list[Any]:
    return [e for e in tracer.replay(trace_id) if e.kind == "maintenance"]


def _compaction(tracer: Tracer, trace_id: str = "t") -> list[Any]:
    return [e for e in tracer.replay(trace_id) if e.kind == "compaction"]


def test_maintenance_emits_step_cost_event() -> None:
    """一次实际节拍 ⇒ 一条 maintenance 事件，含总耗时与三步分步耗时。"""
    tracer = Tracer()
    now = [0.0]
    loop = DefaultLoop(
        memory=MemoryStore(),
        tracer=tracer,
        clock=lambda: now[0],
        maintenance_interval=10.0,
    )

    now[0] = 100.0
    loop._maintain("t", "s1")  # noqa: SLF001 — 直接驱一节拍

    events = _maintenance(tracer)
    assert len(events) == 1
    payload = events[0].payload
    assert set(payload["steps"]) == {"session_compact", "mid_summary", "forget"}
    assert payload["elapsed_ms"] >= 0.0
    assert all(value >= 0.0 for value in payload["steps"].values())


def test_maintenance_cost_event_only_when_tick_runs() -> None:
    """未到节拍间隔 ⇒ 不产成本事件（与维护本身同一闸门）。"""
    tracer = Tracer()
    now = [0.0]
    loop = DefaultLoop(
        memory=MemoryStore(),
        tracer=tracer,
        clock=lambda: now[0],
        maintenance_interval=10.0,
    )

    now[0] = 100.0
    loop._maintain("t", "s1")  # noqa: SLF001 — 首拍
    loop._maintain("t", "s1")  # noqa: SLF001 — 同刻，闸门拦截
    assert len(_maintenance(tracer)) == 1


class _BrokenCompactMemory(MemoryStore):
    def compact(
        self, query: str = "", budget: int = 4096, *, session_id: str = "", deadline: Any = None
    ) -> Any:
        raise RuntimeError("compact boom")  # noqa: TRY003 — 测试用哨兵异常


def test_failed_step_is_attributed_and_others_still_run() -> None:
    """会话压实失败 ⇒ maintenance_failed 带 step 归因；遗忘与成本事件照常。"""
    tracer = Tracer()
    now = [0.0]
    loop = DefaultLoop(
        memory=_BrokenCompactMemory(),
        tracer=tracer,
        clock=lambda: now[0],
        maintenance_interval=10.0,
    )

    now[0] = 100.0
    loop._maintain("t", "s1")  # noqa: SLF001 — 驱一节拍

    events = tracer.replay("t")
    failed = [e for e in events if e.kind == "maintenance_failed"]
    assert len(failed) == 1
    assert failed[0].payload["step"] == "session_compact"
    payload = _maintenance(tracer)[0].payload
    assert "session_compact" in payload["steps"]
    assert "forget" in payload["steps"]


def test_compaction_emits_cost_event_with_steps_and_trigger() -> None:
    """一次轮内压实 ⇒ 一条 compaction 事件，含三步耗时与触发原因。"""
    tracer = Tracer()
    loop = DefaultLoop(memory=MemoryStore(), compactor=Compactor(), tracer=tracer)

    loop._compact(LoopContext(), "t", trigger="budget_retry")  # noqa: SLF001

    events = _compaction(tracer)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["trigger"] == "budget_retry"
    assert set(payload["steps"]) == {"persist", "memory_compact", "forget"}
    assert payload["elapsed_ms"] >= 0.0


_COUNTING_INPUT = 4
_ERROR_INPUT = 2
_COUNTING_OUTPUT = {"conclusions": 2, "decisions": 1, "open_items": 3, "dropped": 1}
_COMPACTION_KEYS = {
    "trigger",
    "elapsed_ms",
    "steps",
    "messages",
    "conclusions",
    "decisions",
    "open_items",
    "dropped",
}


class _CountingCompactor(Compactor):
    def compact(self, history: list[dict[str, Any]]) -> Compaction:
        return Compaction(
            conclusions=["c1", "c2"],
            decisions=["d1"],
            open_items=["o1", "o2", "o3"],
            dropped=["x1"],
        )


class _PersistBrokenCompactor(_CountingCompactor):
    def persist(self, c: Compaction, *, session_id: str = "") -> None:
        raise RuntimeError("persist boom")  # noqa: TRY003 — 测试用哨兵异常


def test_compaction_records_output_and_drop_counts() -> None:
    """`compaction` payload 含五项计数与固定顶层 key 集（change 0263）。"""
    tracer = Tracer()
    loop = DefaultLoop(memory=MemoryStore(), compactor=_CountingCompactor(), tracer=tracer)
    ctx = LoopContext(messages=[{"role": "user", "content": "x"}] * _COUNTING_INPUT)

    loop._compact(ctx, "t")  # noqa: SLF001

    payload = _compaction(tracer)[0].payload
    assert set(payload) == _COMPACTION_KEYS
    assert payload["messages"] == _COUNTING_INPUT
    for key, expected in _COUNTING_OUTPUT.items():
        assert payload[key] == expected


def test_compaction_counts_are_zero_when_compact_raises() -> None:
    """`compact` 抛错 ⇒ 产物四项记 0，`messages` 仍为输入数，事件照常产出。"""
    tracer = Tracer()
    loop = DefaultLoop(memory=MemoryStore(), compactor=_BrokenCompactor(), tracer=tracer)

    loop._compact(LoopContext(messages=[{}] * _ERROR_INPUT), "t")  # noqa: SLF001

    payload = _compaction(tracer)[0].payload
    assert payload["messages"] == _ERROR_INPUT
    for key in ("conclusions", "decisions", "open_items", "dropped"):
        assert payload[key] == 0


def test_compaction_persist_failure_keeps_real_counts() -> None:
    """`persist` 失败不影响已取得的产物计数（失败只影响落盘）。"""
    tracer = Tracer()
    loop = DefaultLoop(memory=MemoryStore(), compactor=_PersistBrokenCompactor(), tracer=tracer)

    loop._compact(LoopContext(messages=[{}]), "t")  # noqa: SLF001

    payload = _compaction(tracer)[0].payload
    assert payload["conclusions"] == _COUNTING_OUTPUT["conclusions"]
    assert payload["dropped"] == _COUNTING_OUTPUT["dropped"]


class _BrokenCompactor(Compactor):
    def compact(self, history: list[dict[str, Any]]) -> Any:
        raise RuntimeError("persist boom")  # noqa: TRY003 — 测试用哨兵异常


def test_compaction_persist_failure_is_attributed() -> None:
    """压实持久化失败 ⇒ step 归因 persist；记忆两步仍执行、成本事件仍产出。"""
    tracer = Tracer()
    loop = DefaultLoop(memory=MemoryStore(), compactor=_BrokenCompactor(), tracer=tracer)

    loop._compact(LoopContext(), "t")  # noqa: SLF001

    events = tracer.replay("t")
    failed = [e for e in events if e.kind == "maintenance_failed"]
    assert len(failed) == 1
    assert failed[0].payload["step"] == "persist"
    payload = _compaction(tracer)[0].payload
    assert payload["trigger"] == "threshold"
    assert set(payload["steps"]) == {"persist", "memory_compact", "forget"}


def test_budget_retry_marks_compaction_trigger() -> None:
    """预算降级触发的压实 ⇒ trigger 为 budget_retry（成本可归因到触发路径）。"""
    tracer = Tracer()
    loop = DefaultLoop(memory=MemoryStore(), compactor=Compactor(), tracer=tracer)

    asyncio.run(
        loop._budget_retry(  # noqa: SLF001
            LoopContext(), "t", budget_retried=False, compacted=False
        )
    )

    triggers = [event.payload["trigger"] for event in _compaction(tracer)]
    assert triggers == ["budget_retry"]


# ---- 轮内压实进度与上限（change 0256） ----


class _CapturingExporter:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def emit(self, events: list[TraceEvent]) -> None:
        self.events.extend(events)


def _echo_provider() -> ToolProvider:
    provider = ToolProvider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.echo",
                description="echo",
                schema={"type": "object", "properties": {"text": {"type": "string"}}},
                coeffects=[],
                reversible=True,
            ),
            handler=lambda text: f"echo:{text}",
        )
    )
    return provider


def _stream(loop: DefaultLoop, prompt: str = "任务") -> list[Any]:
    async def _run() -> list[Any]:
        return [event async for event in loop.astream(prompt)]

    return asyncio.run(_run())


def _one_tool_planner(ctx: LoopContext) -> Action:
    if ctx.rounds == 0:
        return Action(tool_id="tools.echo", args={"text": "x"})
    return Action(args={"reply": "ok"})


def test_compaction_emits_progress_events() -> None:
    """阈值压实前后各一条事件，后含耗时且 timeout=False（change 0256）。"""
    loop = DefaultLoop(
        planner=_one_tool_planner,
        tools=_echo_provider(),
        compactor=Compactor(step_threshold=1),
        tracer=Tracer(),
    )

    events = _stream(loop)
    types = [event.type for event in events]
    assert types.index("loop.compacting") < types.index("loop.compacted")
    compacted = next(event for event in events if event.type == "loop.compacted")
    assert compacted.payload["round"] == 1
    assert compacted.payload["elapsed_ms"] >= 0.0
    assert compacted.payload["timeout"] is False
    assert events[-1].type == "loop_finished"


class _SlowCompactor(Compactor):
    def compact(self, history: list[dict[str, Any]]) -> Any:
        time.sleep(0.2)
        return super().compact(history)


def test_compaction_timeout_is_fail_open() -> None:
    """压实超过上限 ⇒ timeout=True + 留痕 compaction_timeout，本轮正常收尾（change 0256）。"""
    exporter = _CapturingExporter()
    loop = DefaultLoop(
        planner=_one_tool_planner,
        tools=_echo_provider(),
        compactor=_SlowCompactor(step_threshold=1),
        tracer=Tracer(exporter=exporter),
        compact_timeout=0.05,
    )

    events = _stream(loop)

    compacted = next(event for event in events if event.type == "loop.compacted")
    assert compacted.payload["timeout"] is True
    assert events[-1].type == "loop_finished", "压实超时不得阻断本轮"
    failed = [e for e in exporter.events if e.kind == "maintenance_failed"]
    assert [e.payload["step"] for e in failed] == ["compaction_timeout"]
