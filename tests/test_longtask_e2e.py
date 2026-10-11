"""长任务端到端门禁（change 0195 / ADR-0185 / 台账 E132）。

**零 `src/` 改动** —— 只补「端到端锚」，把此前**两端分离**的链路接起来：

- 「压实**产出**摘要」（`test_loop.py` 只断言记忆态）与「摘要**注入** prompt」
  （`test_history_replay.py` 手播摘要）此前**各测一半**，无任何用例断言
  「**上一轮的压实产物出现在下一轮真实装配的 system prompt 里**」。本文件补此锚。
- 同理：滚动摘要越界（change `0193`）与解耦（change `0194`）此前只在**上下文对象**
  （`ctx.summary_long`）层面断言，本文件断言**真实装配后的 system prompt**。

会话归属端到端（checkpoint 会话 ⇒ CLI `--resume` ⇒ `astream` 收到同 session）已由
`test_entry.py::test_task_resume_reuses_checkpoint_session`（change `0190`）承载，**不重复**。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from core.context import Compactor
from core.llm_provider import (
    Embedding,
    LLMChunk,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    TokenUsage,
)
from core.loop import DefaultLoop, LoopEvent
from core.loop.planner import LLMPlanner
from core.memory import MemoryEntry, MemoryStore, TranscriptStore
from core.memory.summarize import build_prompt

_SUMMARY_BLOCK = "历史摘要（长期）："


class _CapturingLLM(LLMProvider):
    """捕获装配后请求的桩 provider（不触网、不真调模型）。"""

    def __init__(self, reply: str = "收到") -> None:
        self.reply = reply
        self.requests: list[LLMRequest] = []

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            content=self.reply,
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1),
            finish_reason="stop",
            provider="stub",
            model="stub",
        )

    async def astream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        self.requests.append(request)
        yield LLMChunk(content=self.reply)

    async def aembedding(self, texts: list[str]) -> list[Embedding]:
        return [Embedding(vector=[1.0, 0.0]) for _ in texts]


def _summarizer_memory() -> MemoryStore:
    """注入纯本地假摘要器（不触网）：压实链路离线可验。"""

    def summarizer(entries: list[MemoryEntry]) -> str:
        return "摘要：" + "；".join(e.content for e in entries)

    return MemoryStore(summarizer=summarizer)


def _episodic(entry_id: str, content: str, session_id: str) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=[],
        source="loop",
        trace_id="prior",
        session_id=session_id,
        kind="episodic",
    )


def _seed_summary(memory: MemoryStore, session_id: str, content: str) -> None:
    """手播一条既有长期摘要（口径同 `MemoryStore._commit_summary` 写入）。"""
    memory.write(
        "L2",
        MemoryEntry(
            id=f"compaction.summary.{session_id}",
            layer="L2",
            content=content,
            tags=["compaction", "summary"],
            source="compaction",
            trace_id=f"compaction.{session_id}",
            session_id=session_id,
            kind="semantic",
        ),
    )


async def _drain(events: AsyncIterator[LoopEvent]) -> list[LoopEvent]:
    return [event async for event in events]


def _system_prompt(llm: _CapturingLLM) -> str:
    return llm.requests[0].messages[0].content


def test_compaction_product_reaches_next_turn_system_prompt(tmp_path: Path) -> None:
    """端到端：**上一轮**压实的产物 → **下一轮**真实装配的 system prompt。

    此前两端分离（`test_loop.py` 只断言记忆态、`test_history_replay.py` 手播摘要）
    ⇒ 无锚能证明「压实真的喂进了下一轮推理」。
    """
    transcript = TranscriptStore(tmp_path / "messages.jsonl")
    memory = _summarizer_memory()
    memory.write("L2", _episodic("prior.0", "上一轮：季度结论 已完成", "s1"))
    llm = _CapturingLLM()
    loop = DefaultLoop(
        planner=LLMPlanner(llm, model="m"),
        transcript=transcript,
        memory=memory,
        compactor=Compactor(memory=memory, step_threshold=100),
        token_budget=1,  # 预算维度触发轮内压实（步数维度不满足）
    )

    asyncio.run(_drain(loop.astream("第一问", session_id="s1")))
    assert memory.summary_for("s1") is not None, "第一轮的轮内压实应产出会话摘要"

    llm.requests.clear()
    asyncio.run(_drain(loop.astream("第二问", session_id="s1")))

    system = _system_prompt(llm)
    assert _SUMMARY_BLOCK in system, "第二轮的 system prompt 应含长期摘要块"
    assert "上一轮：季度结论 已完成" in system, "注入的摘要应为**第一轮压实**的产物（防空过断言）"


def test_over_bound_summary_tail_reaches_compaction_prompt(tmp_path: Path) -> None:
    """端到端（change `0193`）：滚动摘要越界 ⇒ 投喂**摘要器**的既有摘要槽**尾部仍在**。

    注意锚点位置：`_elide_summary` 约束的是**摘要器 prompt 的既有摘要槽**（压实输入），
    **不是**循环注入 system prompt 的内容（后者逐字注入既有摘要，只受预算记账约束）。
    本锚走**真实轮内压实触发**链路（非直接调 `build_prompt`）。
    """
    transcript = TranscriptStore(tmp_path / "messages.jsonl")
    prompts: list[str] = []

    def summarizer(entries: list[MemoryEntry]) -> str:
        prompts.append(build_prompt(entries))  # 捕获真实投喂摘要器的 prompt
        return "摘要：合并完成"

    memory = MemoryStore(summarizer=summarizer)
    memory.write("L2", _episodic("prior.0", "上一轮：新事件", "s1"))
    _seed_summary(memory, "s1", "开头结论。" + "早" * 3000 + "\n最新结论：尾部保真锚点XYZ")
    llm = _CapturingLLM()
    loop = DefaultLoop(
        planner=LLMPlanner(llm, model="m"),
        transcript=transcript,
        memory=memory,
        compactor=Compactor(memory=memory, step_threshold=100),
        token_budget=1,
    )

    asyncio.run(_drain(loop.astream("新一轮", session_id="s1")))

    assert prompts, "轮内压实应至少投喂一次摘要器"
    fed = prompts[0]
    assert "现有摘要：" in fed
    assert "最新结论：尾部保真锚点XYZ" in fed, "越界摘要的**尾部**必须仍进摘要器 prompt（不销毁）"
    assert "⋯（中略" in fed, "越界应有中略标记（证明走的是首尾保留而非全文投喂）"


def test_summary_injected_into_prompt_when_history_replay_disabled(tmp_path: Path) -> None:
    """端到端（change `0194`）：关历史回放（`history_turns=0`）⇒ 摘要仍进**装配后**的 prompt。

    此前只在 `ctx.summary_long` 上下文对象层面断言，本锚验到真实 system prompt。
    """
    transcript = TranscriptStore(tmp_path / "messages.jsonl")
    transcript.append("s1", "user", "历史问")
    transcript.append("s1", "assistant", "历史答")
    memory = _summarizer_memory()
    _seed_summary(memory, "s1", "长期要点：不得删除用户数据。")
    llm = _CapturingLLM()
    loop = DefaultLoop(
        planner=LLMPlanner(llm, model="m"),
        transcript=transcript,
        memory=memory,
        history_turns=0,
    )

    asyncio.run(_drain(loop.astream("新一轮", session_id="s1")))

    messages = llm.requests[0].messages
    system = messages[0].content
    assert _SUMMARY_BLOCK in system and "长期要点：不得删除用户数据。" in system
    assert [m.content for m in messages][1:] == ["新一轮"], "关回放 ⇒ 历史原文不回灌（两通道独立）"
