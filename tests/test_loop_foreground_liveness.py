"""0296 · 前台轮不被后台收尾与压实拖死。

事故：`astream` 在轮首 `await` 上一轮的后台收尾（观察者 + 维护节拍），端点挂起时
下一轮在 `loop_started` 后 **146s 零事件**；同步入口 `run()` 同样无限期等待。

本文件钉住四条边界：下一轮不等待上一轮收尾、后台收尾单链路串行、同步入口有界等待、
维护节拍与轮内压实都带协作式截止。
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from core.context import Compactor
from core.loop import Action, DefaultLoop
from core.memory import MemoryStore
from core.observability import TraceEvent
from core.tools import Tool, ToolDef, ToolProvider

# 截止越过后的维护节拍：压实 + 遗忘两步都应被跳过
_EXPECTED_SKIPPED_MAINTENANCE_STEPS = 2


def _echo(text: str) -> str:
    return f"echo:{text}"


def _echo_tool() -> Tool:
    return Tool(
        definition=ToolDef(
            tool_id="tools.echo",
            description="echo",
            schema={"type": "object", "properties": {"text": {"type": "string"}}},
            coeffects=[],
            reversible=True,
        ),
        handler=_echo,
    )


def _reply_loop(**kwargs: Any) -> DefaultLoop:
    """跑一轮即终止的 loop（一个工具动作，供压实阈值触发）。"""

    def planner(ctx: Any) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "x"})
        return Action(args={"reply": "done"})

    provider = ToolProvider()
    provider.register(_echo_tool())
    return DefaultLoop(planner=planner, tools=provider, max_rounds=3, **kwargs)


class _CaptureTracer:
    """只记 kind 的 tracer 替身（时序断言只需事件名）。"""

    def __init__(self) -> None:
        self.kinds: list[str] = []

    def start_trace(self, task: str) -> str:
        return "t1"

    def end_trace(self, trace_id: str) -> None:
        pass

    def record(self, event: TraceEvent) -> None:
        self.kinds.append(str(event.kind))


def _blocking_observer(
    first_task: str,
    *,
    entered: threading.Event,
    release: threading.Event,
    order: list[str] | None = None,
) -> Any:
    """在指定轮上阻塞的收尾观察者（其余轮立即返回）。"""

    def observer(task: str, steps: list[str], ok: bool, reply: str) -> None:
        if order is not None:
            order.append(task)
        if task != first_task:
            return
        entered.set()
        release.wait(timeout=5.0)

    return observer


def test_next_turn_starts_without_waiting_for_previous_post_turn() -> None:
    """上一轮收尾挂起时，下一轮流式执行 SHALL 立即产出终态并留痕 `post_turn_overlap`。"""
    entered = threading.Event()
    release = threading.Event()
    tracer = _CaptureTracer()

    async def main() -> tuple[list[str], float]:
        loop = _reply_loop(
            turn_observer=_blocking_observer("one", entered=entered, release=release),
            tracer=tracer,
        )
        async for _ in loop.astream("one"):
            pass
        assert await asyncio.to_thread(entered.wait, 2.0), "第一轮收尾确已进入阻塞"
        started = time.monotonic()
        events = [event.type async for event in loop.astream("two")]
        elapsed = time.monotonic() - started
        release.set()
        await loop._await_post_turn(timeout=5.0)  # noqa: SLF001 — 测接缝：收束后台收尾
        return events, elapsed

    events, elapsed = asyncio.run(main())

    assert "loop_finished" in events
    assert elapsed < 0.5, f"下一轮被上一轮收尾拖住（{elapsed:.3f}s）"  # noqa: PLR2004 — 时序上限
    assert "post_turn_overlap" in tracer.kinds


def test_post_turn_chain_is_serial_across_turns() -> None:
    """两轮收尾 SHALL 单链路串行：第二轮观察者排在第一轮结束之后。"""
    entered = threading.Event()
    release = threading.Event()
    order: list[str] = []

    async def main() -> list[str]:
        loop = _reply_loop(
            turn_observer=_blocking_observer("one", entered=entered, release=release, order=order)
        )
        async for _ in loop.astream("one"):
            pass
        assert await asyncio.to_thread(entered.wait, 2.0)
        async for _ in loop.astream("two"):
            pass
        await asyncio.sleep(0.05)  # 给第二轮收尾一次抢跑机会（它必须仍在等第一轮）
        assert order == ["one"], f"第二轮收尾并发启动了：{order}"
        release.set()
        await loop._await_post_turn(timeout=5.0)  # noqa: SLF001 — 测接缝：收束后台收尾
        return order

    assert asyncio.run(main()) == ["one", "two"]


def test_sync_entry_returns_within_post_turn_wait_limit() -> None:
    """`run()` SHALL 在注入的等待上限附近返回，并留痕 `post_turn_timeout`。"""
    entered = threading.Event()
    release = threading.Event()
    tracer = _CaptureTracer()
    loop = _reply_loop(
        turn_observer=_blocking_observer("hi", entered=entered, release=release),
        post_turn_wait_timeout=0.1,
        tracer=tracer,
    )

    started = time.monotonic()
    result = loop.run("hi")
    elapsed = time.monotonic() - started
    release.set()

    assert result.reply == "done"
    assert entered.is_set(), "收尾观察者确已启动"
    assert elapsed < 1.0, f"同步入口被收尾拖住（{elapsed:.3f}s）"  # noqa: PLR2004 — 时序上限
    assert "post_turn_timeout" in tracer.kinds


class _MaintenanceMemory(MemoryStore):
    """维护节拍替身：压实推进注入时钟，记录截止与遗忘次数。"""

    def __init__(self, clock: list[float]) -> None:
        super().__init__()
        self._advance = clock
        self.deadlines: list[float | None] = []
        self.forgets = 0

    def compact(
        self,
        query: str = "",
        budget: int = 4096,
        *,
        session_id: str = "",
        deadline: float | None = None,
    ) -> Any:
        self.deadlines.append(deadline)
        self._advance[0] += 50.0
        return None

    def forget(self, *, threshold: float = 0.0) -> list[str]:
        self.forgets += 1
        return []


def test_maintenance_skips_remaining_steps_after_deadline() -> None:
    """维护节拍越过总时长上限后 SHALL 跳过后续步骤并逐项留痕。"""
    now = [0.0]
    memory = _MaintenanceMemory(now)
    tracer = _CaptureTracer()
    loop = _reply_loop(
        memory=memory,
        clock=lambda: now[0],
        maintenance_interval=1.0,
        maintenance_timeout=10.0,
        tracer=tracer,
    )
    now[0] = 2.0  # 距上次维护 2s ≥ 1s ⇒ 节拍触发；截止 = 2 + 10 = 12

    loop._maintain("t1", "s1")  # noqa: SLF001 — 测接缝：直接驱动维护节拍

    assert memory.deadlines == [12.0], "压实必须收到协作式截止"
    assert memory.forgets == 0, "截止后不得执行遗忘归档"
    assert tracer.kinds.count("maintenance_failed") == _EXPECTED_SKIPPED_MAINTENANCE_STEPS
    assert "maintenance" in tracer.kinds


class _RecordingMemory(MemoryStore):
    """轮内压实替身：只记录收到的截止时间。"""

    def __init__(self) -> None:
        super().__init__()
        self.deadlines: list[float | None] = []

    def compact(
        self,
        query: str = "",
        budget: int = 4096,
        *,
        session_id: str = "",
        deadline: float | None = None,
    ) -> Any:
        self.deadlines.append(deadline)
        return None


def test_in_loop_compaction_receives_cooperative_deadline() -> None:
    """轮内压实 SHALL 把 `compact_timeout` 派生的截止时间传给 `MemoryStore.compact`。"""
    memory = _RecordingMemory()
    loop = _reply_loop(
        memory=memory,
        compactor=Compactor(memory=memory, step_threshold=1),
        compact_timeout=5.0,
        clock=lambda: 0.0,
    )

    loop.run("hi")

    assert memory.deadlines == [5.0]
