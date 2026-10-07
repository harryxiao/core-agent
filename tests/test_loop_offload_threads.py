"""0167 · 收尾与维护中的同步模型调用：卸载出事件循环（承 ADR-0157）。

事故：组合根的 `_llm_text` 是**同步**接缝（内部 `LLMProvider.completion()` = `asyncio.run`），
却被 loop 在**事件循环内同步调用**（压实 / 收尾钩子 / 冷路径）⇒ `RuntimeError: asyncio.run()
cannot be called from a running event loop` ⇒ 被既有降级链吞成一条遥测 ⇒ **摘要（G3 的输入）与
关键事实抽取（G4）从未落库**。

本文件把「在工作线程上执行」钉成可执行判据：**工作线程上没有运行中的事件循环**
（`asyncio.get_running_loop()` 抛 `RuntimeError`），以及**事件循环在压实期间仍能推进其他任务**。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from core.context import Compactor
from core.llm_provider import (
    Embedding,
    LLMChunk,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    Message,
    TokenUsage,
)
from core.loop import Action, DefaultLoop
from core.memory import MemoryEntry, MemoryStore, summarize_with
from core.tools import Tool, ToolDef, ToolProvider

_BLOCK_S = 0.3  # 压实替身的阻塞时长（远大于事件循环的一个 tick）
_MIN_TICKS = 5  # 阻塞期间事件循环应推进的最小 tick 数（~ _BLOCK_S / ticker 周期 / 2）


def _on_loop_thread() -> bool:
    """当前是否在**有运行中事件循环**的线程上（True ⇒ 事件循环会被这类工作阻塞）。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


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


class _SyncBridgeProvider(LLMProvider):
    """只实现异步入口 ⇒ 继承的 `completion()` 即 `asyncio.run` 薄壳（**事故现场的原样**）。"""

    def __init__(self) -> None:
        self.calls: list[bool] = []  # 同步桥接调用点落在哪个线程（True = 有运行中循环）

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="提炼结果",
            usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
            finish_reason="stop",
            provider="stub",
            model="stub",
        )

    async def astream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        yield LLMChunk(content="x")

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        return [Embedding(vector=[0.1]) for _ in texts]


def _sync_bridge(provider: _SyncBridgeProvider):
    """把**同步**模型桥接适配为 memory 摘要契约（与组合根 `_llm_text` 同形）。

    调用点（`provider.completion` 之前）即「同步桥接落在哪个线程」的观测点 ——
    `acompletion` 内部另有 `asyncio.run` 造的循环，不是被观测的对象。
    """

    def _text(prompt: str) -> str:
        provider.calls.append(_on_loop_thread())
        response = provider.completion(
            LLMRequest(messages=[Message(role="user", content=prompt)], model="stub")
        )
        return response.content

    return _text


def _prior_entry() -> MemoryEntry:
    return MemoryEntry(
        id="loop.prior",
        layer="L2",
        content="上一轮：结论 完成",
        tags=["loop"],
        source="loop",
        trace_id="prior",
        session_id="s1",
    )


def _reply_loop(**kwargs: Any) -> DefaultLoop:
    """跑一轮即终止的 loop（收尾面全开：观察者 / 冷路径走注入）。"""

    def planner(ctx: Any) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "结论"})
        return Action(args={"reply": "done"})

    provider = ToolProvider()
    provider.register(_echo_tool())
    return DefaultLoop(planner=planner, tools=provider, max_rounds=3, **kwargs)


# ---- ① 三处边界都在工作线程上（无运行中事件循环） ----


def test_turn_observer_runs_off_loop_thread() -> None:
    """收尾钩子在**无运行中事件循环**的线程上被调用（同步模型桥接因此可用）。"""
    on_loop: list[bool] = []

    def observer(task: str, steps: list[str], ok: bool) -> None:
        on_loop.append(_on_loop_thread())

    _reply_loop(turn_observer=observer).run("hi")

    assert on_loop == [False], "收尾钩子必须落在工作线程（旧实现为 True）"


def test_cold_path_runs_off_loop_thread() -> None:
    """冷路径回调在**无运行中事件循环**的线程上被调用。"""
    clock = [0.0]
    on_loop: list[bool] = []

    def cold_path() -> None:
        on_loop.append(_on_loop_thread())

    loop = _reply_loop(maintenance_interval=1.0, clock=lambda: clock[0], cold_path=cold_path)
    clock[0] = 5.0  # 距上次维护 5s ≥ 1s ⇒ 节拍触发

    loop.run("hi")

    assert on_loop == [False], "冷路径回调必须落在工作线程（旧实现为 True）"


# ---- ② 压实不阻塞事件循环 ----


class _BlockingMemory(MemoryStore):
    """压实替身：真阻塞（`time.sleep`）以暴露「是否占用事件循环线程」。"""

    def __init__(self) -> None:
        super().__init__()
        self.compacted = 0
        self.on_loop = True

    def compact(self, session_id: str = "") -> Any:  # type: ignore[override]
        self.compacted += 1
        self.on_loop = _on_loop_thread()
        time.sleep(_BLOCK_S)
        return super().compact(session_id)


def test_event_loop_not_blocked_during_compaction() -> None:
    """压实**阻塞**期间，事件循环仍能推进其他协程任务（旧实现下 ticks ≈ 0）。"""
    memory = _BlockingMemory()

    async def main() -> int:
        ticks = 0

        async def ticker() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        task = asyncio.create_task(ticker())
        loop = _reply_loop(memory=memory, compactor=Compactor(memory=memory, round_threshold=1))
        async for _ in loop.astream("hi"):
            pass
        task.cancel()
        return ticks

    ticks = asyncio.run(main())

    assert memory.compacted >= 1, "压实确已触发（否则本用例没测到东西）"
    assert memory.on_loop is False, "压实必须落在工作线程"
    assert ticks >= _MIN_TICKS, f"压实期间事件循环应持续推进（实测 {ticks} 次）"


# ---- ③ 端到端：同步模型桥接的摘要真的落库 ----


def test_summary_written_with_sync_llm_bridge() -> None:
    """同步模型桥接（`asyncio.run` 形态）的摘要**被写入**（旧实现被 RuntimeError 吞掉）。"""
    provider = _SyncBridgeProvider()
    memory = MemoryStore(summarizer=summarize_with(_sync_bridge(provider)))
    memory.write("L2", _prior_entry())
    loop = _reply_loop(memory=memory, compactor=Compactor(memory=memory, round_threshold=1))

    loop.run("hi")

    summary = {e.id: e for e in memory.audit()}.get("compaction.summary.s1")
    assert summary is not None, "压实摘要必须落库（旧实现：RuntimeError 被降级链吞掉、摘要恒缺）"
    assert "提炼结果" in summary.content
    assert provider.calls == [False], "同步模型调用必须落工作线程"


# ---- ④ 降级语义零回归 ----


def test_turn_observer_failure_still_degrades() -> None:
    """观察者抛错仍只降级留痕：本轮回复与终态零回归。"""
    traced: list[str] = []

    def observer(task: str, steps: list[str], ok: bool) -> None:
        raise RuntimeError("boom")

    class _Tracer:
        def start_trace(self, task: str) -> str:
            return "t1"

        def end_trace(self, trace_id: str) -> None:
            pass

        def record(self, event: Any) -> None:
            traced.append(str(event.kind))

    loop = _reply_loop(turn_observer=observer, tracer=_Tracer())

    result = loop.run("hi")

    assert result.reply == "done"
    assert result.failed is False
    assert "turn_observer_failed" in traced
