"""会话历史回灌（change 0115 / B1）：环路载入本会话最近历史 → 推理请求按序组装。

对应规格：`doc/openspec/specs/loop/spec.md`「执行循环」的历史载入/回灌条款。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

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
from core.memory import TranscriptStore


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
