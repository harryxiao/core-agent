"""会话历史回灌（change 0115 / B1）：环路载入本会话最近历史 → 推理请求按序组装。

对应规格：`doc/openspec/specs/loop/spec.md`「执行循环」的历史载入/回灌条款。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from core.llm_provider import (
    Embedding,
    LLMChunk,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    Message,
    TokenUsage,
)
from core.loop import Action, DefaultLoop, LoopContext, LoopEvent
from core.loop.default import _action_steps, _task_text
from core.loop.planner import LLMPlanner
from core.memory import MemoryEntry, MemoryStore, TranscriptStore


class _CapturingLLM(LLMProvider):
    """捕获推理请求的桩 provider（本文件不触网、不真调模型）。"""

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            content="收到",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
            finish_reason="stop",
            provider="stub",
            model="stub",
        )

    async def astream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        self.requests.append(request)
        yield LLMChunk(content="收到")

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        return [Embedding(vector=[1.0, 0.0]) for _ in texts]


async def _drain(events: AsyncIterator[LoopEvent]) -> list[LoopEvent]:
    return [event async for event in events]


def _transcript(tmp_path: Path, *pairs: tuple[str, str], session_id: str = "s1") -> TranscriptStore:
    store = TranscriptStore(tmp_path / "messages.jsonl")
    for question, answer in pairs:
        store.append(session_id, "user", question)
        store.append(session_id, "assistant", answer)
    return store


# ---- 回灌：请求组装次序 ----


def test_history_replayed_between_system_and_current_turn(tmp_path: Path) -> None:
    store = _transcript(tmp_path, ("第一问", "第一答"))
    llm = _CapturingLLM()
    loop = DefaultLoop(planner=LLMPlanner(llm, model="m"), transcript=store)

    asyncio.run(_drain(loop.astream("第二问", session_id="s1")))

    (request,) = llm.requests
    assert [m.role for m in request.messages] == ["system", "user", "assistant", "user"]
    assert [m.content for m in request.messages][1:3] == ["第一问", "第一答"]
    assert request.messages[-1] == Message(role="user", content="第二问")


def test_history_turns_bound_limits_replayed_rounds(tmp_path: Path) -> None:
    store = _transcript(tmp_path, ("第一问", "第一答"), ("第二问", "第二答"))
    llm = _CapturingLLM()
    loop = DefaultLoop(planner=LLMPlanner(llm, model="m"), transcript=store, history_turns=1)

    asyncio.run(_drain(loop.astream("第三问", session_id="s1")))

    (request,) = llm.requests
    assert [m.content for m in request.messages][1:] == ["第二问", "第二答", "第三问"]


def test_history_turns_zero_disables_replay(tmp_path: Path) -> None:
    store = _transcript(tmp_path, ("第一问", "第一答"))
    llm = _CapturingLLM()
    loop = DefaultLoop(planner=LLMPlanner(llm, model="m"), transcript=store, history_turns=0)

    asyncio.run(_drain(loop.astream("第二问", session_id="s1")))

    (request,) = llm.requests
    assert [m.role for m in request.messages] == ["system", "user"]  # 只剩系统提示 + 本轮
    assert request.messages[-1] == Message(role="user", content="第二问")


# ---- 本轮消息语义不被历史打破（四处 accessor） ----


def test_current_turn_accessors_see_only_this_turn(tmp_path: Path) -> None:
    store = _transcript(tmp_path, ("历史任务", "历史答复"))
    loop = DefaultLoop(planner=LLMPlanner(_CapturingLLM(), model="m"), transcript=store)

    ctx = loop.perceive("本轮任务", session_id="s1")

    assert ctx.messages == [{"role": "user", "content": "本轮任务"}]  # 历史不进 messages
    assert _task_text(ctx) == "本轮任务"
    assert _action_steps(ctx) == []
    assert loop._echo(ctx) == "已完成：本轮任务"  # noqa: SLF001 — 内建回显路径
    assert LLMPlanner._task(ctx) == "本轮任务"
    assert [entry["content"] for entry in ctx.history] == ["历史任务", "历史答复"]


# ---- 历史 token 计入预算记账 ----


def test_history_tokens_counted_into_budget(tmp_path: Path) -> None:
    store = _transcript(tmp_path, ("x" * 400, "y" * 400))  # 各 100 token
    seen: list[int] = []

    def planner(ctx: LoopContext) -> Action:
        seen.append(ctx.token_used)
        return Action(args={"reply": "ok"})

    loop = DefaultLoop(planner=planner, transcript=store, token_budget=100_000)
    asyncio.run(_drain(loop.astream("z" * 40, session_id="s1")))  # 本轮 user 10 token

    assert seen == [210]


# ---- 逐字兼容：无转录 / 空标识 ----


def test_no_transcript_means_no_history() -> None:
    seen: list[list[object]] = []

    def planner(ctx: LoopContext) -> Action:
        seen.append(list(ctx.history))
        return Action(args={"reply": "ok"})

    loop = DefaultLoop(planner=planner)  # 未注入 transcript
    asyncio.run(_drain(loop.astream("任务", session_id="s1")))

    assert seen == [[]]


def test_empty_session_id_never_replays(tmp_path: Path) -> None:
    store = _transcript(tmp_path, ("第一问", "第一答"))
    seen: list[list[object]] = []

    def planner(ctx: LoopContext) -> Action:
        seen.append(list(ctx.history))
        return Action(args={"reply": "ok"})

    loop = DefaultLoop(planner=planner, transcript=store)
    asyncio.run(_drain(loop.astream("任务")))  # 未指定会话标识

    assert seen == [[]]
    assert [e["role"] for e in store.read("s1")] == ["user", "assistant"]  # 本轮未追加


# ---- 三层滑窗：短/中/长（change 0178 / ADR-0169 / 台账 E115） ----


def _summary_memory(
    session_id: str, *, long: str = "长期要点", mid: str = "中期要点"
) -> MemoryStore:
    """预置两条会话摘要（长期 + 中期）的只读记忆桩。"""
    memory = MemoryStore()
    memory.write(
        "L2",
        MemoryEntry(
            id=f"compaction.summary.{session_id}",
            layer="L2",
            content=long,
            tags=["compaction", "summary"],
            source="compaction",
            trace_id=f"compaction.{session_id}",
            session_id=session_id,
            kind="semantic",
        ),
    )
    memory.write(
        "L2",
        MemoryEntry(
            id=f"compaction.mid.{session_id}",
            layer="L2",
            content=mid,
            tags=["compaction", "mid"],
            source="compaction",
            trace_id=f"compaction.mid.{session_id}",
            session_id=session_id,
            kind="semantic",
        ),
    )
    return memory


def _l2_entry(entry_id: str, content: str, session_id: str) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=[],
        source="loop",
        trace_id="t",
        session_id=session_id,
        kind="episodic",
    )


def test_cold_session_request_verbatim_without_summaries(tmp_path: Path) -> None:
    """I5 核心：无任何摘要 ⇒ `tiered=False` ⇒ 请求逐字 = 今天（无摘要块）。"""
    store = _transcript(tmp_path, ("第一问", "第一答"))
    llm = _CapturingLLM()
    loop = DefaultLoop(planner=LLMPlanner(llm, model="m"), transcript=store, memory=MemoryStore())

    asyncio.run(_drain(loop.astream("第二问", session_id="s1")))

    (request,) = llm.requests
    assert [m.role for m in request.messages] == ["system", "user", "assistant", "user"]
    assert [m.content for m in request.messages][1:3] == ["第一问", "第一答"]
    assert "历史摘要" not in request.messages[0].content


def test_layered_summaries_injected_as_system_blocks(tmp_path: Path) -> None:
    store = _transcript(tmp_path, ("第一问", "第一答"))
    llm = _CapturingLLM()
    loop = DefaultLoop(
        planner=LLMPlanner(llm, model="m"),
        transcript=store,
        memory=_summary_memory("s1"),
    )

    asyncio.run(_drain(loop.astream("第二问", session_id="s1")))

    system = llm.requests[0].messages[0].content
    assert "历史摘要（长期）：\n长期要点" in system
    assert "历史摘要（中期）：\n中期要点" in system


def test_long_before_mid_and_after_pinned_notes(tmp_path: Path) -> None:
    store = _transcript(tmp_path, ("第一问", "第一答"))
    llm = _CapturingLLM()
    loop = DefaultLoop(
        planner=LLMPlanner(llm, model="m"),
        transcript=store,
        memory=_summary_memory("s1"),
        pinned_notes_consult=lambda: "不得删除用户数据。",
    )

    asyncio.run(_drain(loop.astream("第二问", session_id="s1")))

    system = llm.requests[0].messages[0].content
    assert (
        system.index("常驻笔记")
        < system.index("历史摘要（长期）")
        < system.index("历史摘要（中期）")
    )


def test_summaries_not_folded_into_history_or_messages(tmp_path: Path) -> None:
    store = _transcript(tmp_path, ("第一问", "第一答"))
    loop = DefaultLoop(
        planner=LLMPlanner(_CapturingLLM(), model="m"),
        transcript=store,
        memory=_summary_memory("s1"),
    )

    ctx = loop.perceive("第二问", session_id="s1")

    assert ctx.summary_long == "长期要点"
    assert ctx.summary_mid == "中期要点"
    assert [entry["content"] for entry in ctx.history] == ["第一问", "第一答"]  # 未折入
    assert ctx.messages == [{"role": "user", "content": "第二问"}]  # 未折入


@pytest.mark.parametrize(
    ("turns", "sid", "with_transcript"),
    [(20, "", True), (20, "s1", False)],
)
def test_summaries_gated_on_session_and_transcript(
    tmp_path: Path, turns: int, sid: str, with_transcript: bool
) -> None:
    """空标识 / 未注入转录 ⇒ 摘要不读不注入（**本职**门控，change 0194 后仍如此）。

    「关历史回放」不再属此列 —— 见 `test_summaries_injected_when_history_replay_disabled`。
    """
    store = _transcript(tmp_path, ("第一问", "第一答")) if with_transcript else None
    seen: list[tuple[str, str, list[object]]] = []

    def planner(ctx: LoopContext) -> Action:
        seen.append((ctx.summary_long, ctx.summary_mid, list(ctx.history)))
        return Action(args={"reply": "ok"})

    loop = DefaultLoop(
        planner=planner,
        transcript=store,
        memory=_summary_memory("s1"),
        history_turns=turns,
    )
    asyncio.run(_drain(loop.astream("第二问", session_id=sid)))

    assert seen == [("", "", [])]


def test_summaries_injected_when_history_replay_disabled(tmp_path: Path) -> None:
    """摘要注入与 `loop.history_turns` **解耦**（change 0194 / ADR-0184 / 台账 E131）。

    关历史回放（`history_turns=0`）只关**原文回灌**，SHALL NOT 连坐关掉摘要注入 ——
    变更前该会话的摘要被静默丢弃（长任务失忆来源之一）。
    """
    store = _transcript(tmp_path, ("第一问", "第一答"))
    loop = DefaultLoop(
        planner=LLMPlanner(_CapturingLLM(), model="m"),
        transcript=store,
        memory=_summary_memory("s1"),
        history_turns=0,
    )

    ctx = loop.perceive("第二问", session_id="s1")

    assert ctx.summary_long == "长期要点", "关回放不减摘要（长期）"
    assert ctx.summary_mid == "中期要点", "关回放不减摘要（中期）"
    assert ctx.history == [], "关回放 ⇒ 历史带确为空（两通道各自独立）"


def test_history_replay_default_still_unchanged_after_decoupling(tmp_path: Path) -> None:
    """缺省（`history_turns > 0`）⇒ 摘要与历史回灌**逐字不变**（兼容性红线）。"""
    store = _transcript(tmp_path, ("第一问", "第一答"))
    llm = _CapturingLLM()
    loop = DefaultLoop(
        planner=LLMPlanner(llm, model="m"),
        transcript=store,
        memory=_summary_memory("s1"),
    )

    asyncio.run(_drain(loop.astream("第二问", session_id="s1")))

    system = llm.requests[0].messages[0].content
    assert "历史摘要（长期）：\n长期要点" in system
    assert [m.content for m in llm.requests[0].messages][1:3] == ["第一问", "第一答"]


def test_load_summaries_docstring_states_decoupling() -> None:
    """诚实化（change 0194）：门控注释不再称「与 `_load_history` 完全同形」。"""
    doc = DefaultLoop._load_summaries.__doc__ or ""  # noqa: SLF001 — 文档面断言
    assert "完全同形" not in doc
    assert "解耦" in doc


def test_tiered_short_band_narrows_and_drops_older_turns(tmp_path: Path) -> None:
    """分层激活 ⇒ 短带按比例收窄（`history_turns=4` ⇒ 短 2 轮），更旧轮不再回灌原文。"""
    store = _transcript(tmp_path, *[(f"问{i}", f"答{i}") for i in range(8)])
    llm = _CapturingLLM()
    loop = DefaultLoop(
        planner=LLMPlanner(llm, model="m"),
        transcript=store,
        memory=_summary_memory("s1"),
        history_turns=4,
    )

    asyncio.run(_drain(loop.astream("新问", session_id="s1")))

    contents = [m.content for m in llm.requests[0].messages]
    assert contents[1:5] == ["问6", "答6", "问7", "答7"], "短带 = 末 2 轮原文"
    assert "问4" not in contents, "中带轮（问 4/5）不进原文，由中期摘要承接"


def test_maintain_materializes_long_and_mid_summaries(tmp_path: Path) -> None:
    """一次维护节拍产出会话压实（长期）+ 中带物化（中期）两条摘要。"""
    store = _transcript(tmp_path, *[(f"问{i}", f"答{i}") for i in range(8)])
    memory = MemoryStore(
        summarizer=lambda entries: "摘要：" + "；".join(e.content for e in entries)
    )
    memory.write("L2", _l2_entry("e0", "会话事实", "s1"))
    now = [0.0]
    loop = DefaultLoop(
        planner=LLMPlanner(_CapturingLLM(), model="m"),
        transcript=store,
        memory=memory,
        history_turns=4,
        clock=lambda: now[0],
        maintenance_interval=10.0,
    )

    now[0] = 100.0
    loop._maintain("t-1", "s1")  # noqa: SLF001 — 直接驱一节拍

    assert memory.summary_for("s1") is not None, "会话压实产出长期摘要"
    assert memory.mid_summary_for("s1") is not None, "中带物化产出中期摘要"


def test_maintain_mid_failure_degrades_without_raising(tmp_path: Path) -> None:
    """I6：中层物化失败降级（留痕），不中断维护、不抛出。"""
    store = _transcript(tmp_path, *[(f"问{i}", f"答{i}") for i in range(8)])

    class _BrokenSliceMemory(MemoryStore):
        def summarize_slice(
            self, session_id: str, entries: list[Any], *, max_chars: int
        ) -> str | None:
            raise RuntimeError("slice boom")  # noqa: TRY003 — 测试用哨兵异常

    now = [0.0]
    loop = DefaultLoop(
        planner=LLMPlanner(_CapturingLLM(), model="m"),
        transcript=store,
        memory=_BrokenSliceMemory(),
        history_turns=4,
        clock=lambda: now[0],
        maintenance_interval=10.0,
    )

    now[0] = 100.0
    loop._maintain("t-1", "s1")  # noqa: SLF001 — 不抛即通过


def test_load_summaries_failure_degrades_to_empty(tmp_path: Path) -> None:
    """I7：摘要读取失败 ⇒ 降级为空（不回灌），本轮不破。"""
    store = _transcript(tmp_path, ("第一问", "第一答"))

    class _BrokenMidMemory(MemoryStore):
        def mid_summary_for(self, session_id: str) -> MemoryEntry | None:
            raise RuntimeError("mid boom")  # noqa: TRY003 — 测试用哨兵异常

    seen: list[tuple[str, str]] = []

    def planner(ctx: LoopContext) -> Action:
        seen.append((ctx.summary_long, ctx.summary_mid))
        return Action(args={"reply": "ok"})

    loop = DefaultLoop(planner=planner, transcript=store, memory=_BrokenMidMemory())
    asyncio.run(_drain(loop.astream("第二问", session_id="s1")))

    assert seen == [("", "")]
