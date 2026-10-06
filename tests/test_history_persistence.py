"""本轮对话落盘（change 0115 / B1）：收尾追加「用户原话 + 最终回复」。

对应规格：`doc/openspec/specs/loop/spec.md`「执行循环」的转录追加条款。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest

from core.loop import Action, DefaultLoop, LoopContext, LoopEvent
from core.memory import MemoryStore, TranscriptStore


class _ExplodingMemory:
    """写入必炸的记忆替身：验证转录落盘不依赖记忆链路。"""

    def write(self, layer: str, entry: Any) -> None:
        raise RuntimeError("记忆写入失败")

    def read(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


async def _drain(events: AsyncIterator[LoopEvent]) -> list[LoopEvent]:
    return [event async for event in events]


def _planner(reply: str = "收到"):
    def planner(ctx: LoopContext) -> Action:
        return Action(args={"reply": reply})

    return planner


def test_successful_turn_appends_user_and_reply(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path / "messages.jsonl")
    loop = DefaultLoop(planner=_planner(), transcript=store)

    asyncio.run(_drain(loop.astream("第一问", session_id="s1")))

    entries = store.read("s1")
    assert [(e["role"], e["content"]) for e in entries] == [
        ("user", "第一问"),
        ("assistant", "收到"),
    ]


def test_second_turn_makes_history_grow(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path / "messages.jsonl")
    loop = DefaultLoop(planner=_planner(), transcript=store)

    asyncio.run(_drain(loop.astream("第一问", session_id="s1")))
    asyncio.run(_drain(loop.astream("第二问", session_id="s1")))

    assert [e["content"] for e in store.read("s1")] == ["第一问", "收到", "第二问", "收到"]


def test_turn_failed_with_synthetic_reply_writes_no_reply(tmp_path: Path) -> None:
    """轮次耗尽 ⇒ 回复是**合成**终止文案，SHALL NOT 当作模型原话落盘；用户原话仍在。"""
    store = TranscriptStore(tmp_path / "messages.jsonl")
    loop = DefaultLoop(planner=_planner(), transcript=store, max_rounds=0)

    events = asyncio.run(_drain(loop.astream("无解的问题", session_id="s1")))

    assert any(event.type == "loop_failed" for event in events)
    entries = store.read("s1")
    assert [(e["role"], e["content"]) for e in entries] == [("user", "无解的问题")]


def test_transcript_lands_before_memory_write(tmp_path: Path) -> None:
    """转录追加先于 ``remember``：记忆写入炸掉不影响已落盘的对话。

    （记忆失败向调用方传播是**既有**行为，本 change 不改；此处只钉住次序与独立性。）
    """
    store = TranscriptStore(tmp_path / "messages.jsonl")
    loop = DefaultLoop(
        planner=_planner(),
        transcript=store,
        memory=cast("MemoryStore", _ExplodingMemory()),
    )

    with pytest.raises(RuntimeError, match="记忆写入失败"):
        asyncio.run(_drain(loop.astream("第一问", session_id="s1")))

    assert [(e["role"], e["content"]) for e in store.read("s1")] == [
        ("user", "第一问"),
        ("assistant", "收到"),
    ]


def test_user_line_survives_later_failure(tmp_path: Path) -> None:
    """用户原话在 ``perceive`` 就落盘（先于任何 yield）⇒ 后续推理失败也不丢。"""

    def planner(ctx: LoopContext) -> Action:
        raise RuntimeError("推理失败")

    store = TranscriptStore(tmp_path / "messages.jsonl")
    loop = DefaultLoop(planner=planner, transcript=store)

    with pytest.raises(RuntimeError, match="推理失败"):
        asyncio.run(_drain(loop.astream("第一问", session_id="s1")))

    assert [(e["role"], e["content"]) for e in store.read("s1")] == [("user", "第一问")]


def test_empty_session_id_writes_nothing(tmp_path: Path) -> None:
    store = TranscriptStore(tmp_path / "messages.jsonl")
    loop = DefaultLoop(planner=_planner(), transcript=store)

    asyncio.run(_drain(loop.astream("未归属的一轮")))

    assert store.read("") == []
    assert not (tmp_path / "messages.jsonl").exists()
