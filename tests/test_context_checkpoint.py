"""上下文淘汰的情景检查点（change 0310 / ADR-0300）。

钉住：滑出保留窗口的转录行**立即**回写为 `context_checkpoint` 情景记录（SDD §4.5 / §6.7
Tier 3 / A5）——记录带 `(seq_from, seq_to)` 日志水位与 `artifact:` 工件引用，内容为脱敏有界
摘要；只写**新增**淘汰区间（水位增量 + 确定性 id 双重防重）；开关关闭 / 无保留窗口 / 未接线
⇒ 零写入；回写失败只告警、不阻断本轮。
"""

from __future__ import annotations

import asyncio
import json
import warnings
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from core.context import (
    CHECKPOINT_TAG,
    MAX_CHECKPOINT_CHARS,
    MAX_CHECKPOINT_LINE_CHARS,
    checkpoint_artifacts,
    checkpoint_summary,
)
from core.loop import Action, DefaultLoop, LoopContext, LoopEvent
from core.loop.default import _round_artifacts
from core.memory import REDACTED, MemoryEntry, MemoryStore, TranscriptStore
from core.plugin_registry import EffectTracker

_SECRET = "sk-abcdefgh12345678"


async def _drain(events: AsyncIterator[LoopEvent]) -> list[LoopEvent]:
    return [event async for event in events]


def _transcript(tmp_path: Path, *pairs: tuple[str, str], session_id: str = "s1") -> TranscriptStore:
    store = TranscriptStore(tmp_path / "messages.jsonl")
    for question, answer in pairs:
        store.append(session_id, "user", question)
        store.append(session_id, "assistant", answer)
    return store


def _memory() -> MemoryStore:
    return MemoryStore(effect_tracker=EffectTracker())


def _loop(
    memory: MemoryStore,
    transcript: TranscriptStore,
    *,
    history_turns: int = 1,
    enabled: bool = True,
) -> DefaultLoop:
    return DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "完成"}),
        memory=memory,
        transcript=transcript,
        history_turns=history_turns,
        context_checkpoint=enabled,
    )


def _checkpoints(memory: MemoryStore) -> list[MemoryEntry]:
    return [entry for entry in memory.audit() if CHECKPOINT_TAG in entry.tags]


# ---- 转录工件列 ----


def test_transcript_rows_carry_optional_artifacts(tmp_path: Path) -> None:
    store = _transcript(tmp_path, ("问", "答"))
    store.append("s1", "assistant", "再答", artifacts=["a.py", "b.py"])

    rows = store.read("s1")

    assert rows[1].get("artifacts") is None  # 旧格式行不凭空长键
    assert rows[2]["artifacts"] == ["a.py", "b.py"]


def test_in_memory_transcript_keeps_artifacts() -> None:
    store = TranscriptStore()
    store.append("s1", "assistant", "答", artifacts=["a.py"])

    assert store.read("s1")[0]["artifacts"] == ["a.py"]


def test_round_artifacts_collects_written_paths_only() -> None:
    ctx = LoopContext(
        messages=[
            {"role": "user", "content": "写文件"},
            _action("tools.file_write", {"path": "a.py"}),
            {"role": "tool", "content": '{"data": {"path": "a.py"}}'},
            _action("tools.file_read", {"path": "b.py"}),
            _action("tools.file_patch", {"path": "a.py"}),
            _action("tools.file_patch", {"path": "c.py"}),
        ]
    )

    assert _round_artifacts(ctx) == ["a.py", "c.py"]


def _action(tool_id: str, args: dict[str, Any]) -> dict[str, str]:
    return {"role": "assistant", "content": json.dumps({"tool_id": tool_id, "args": args})}


# ---- 淘汰前缀切分 ----


def test_evicted_prefix_matches_short_band(tmp_path: Path) -> None:
    store = _transcript(tmp_path, ("问1", "答1"), ("问2", "答2"), ("问3", "答3"))

    seq_from, rows = store.evicted_prefix("s1", short_turns=1, mid_turns=0, short_tokens=0)

    assert seq_from == 4  # noqa: PLR2004 — 行序断言
    assert [row["content"] for row in rows] == ["问1", "答1", "问2", "答2"]


def test_evicted_prefix_starts_at_mid_band(tmp_path: Path) -> None:
    store = _transcript(tmp_path, ("问1", "答1"), ("问2", "答2"), ("问3", "答3"))

    seq_from, rows = store.evicted_prefix("s1", short_turns=1, mid_turns=1, short_tokens=0)

    assert seq_from == 2  # noqa: PLR2004 — 行序断言
    assert [row["content"] for row in rows] == ["问1", "答1"]


def test_evicted_prefix_empty_when_all_retained(tmp_path: Path) -> None:
    store = _transcript(tmp_path, ("问1", "答1"))

    assert store.evicted_prefix("s1", short_turns=5, mid_turns=0, short_tokens=0) == (0, [])


# ---- 回写 ----


def test_eviction_writes_context_checkpoint(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, ("问1", "答1"), ("问2", "答2"), ("问3", "答3"))
    memory = _memory()
    loop = _loop(memory, transcript)

    asyncio.run(_drain(loop.astream("问4", session_id="s1")))

    (checkpoint,) = _checkpoints(memory)
    assert checkpoint.id == "context_checkpoint.s1.3"
    assert checkpoint.layer == "L2"
    assert checkpoint.kind == "episodic"
    assert checkpoint.source == "context"
    assert checkpoint.session_id == "s1"
    assert "seq_from:0" in checkpoint.tags
    assert "seq_to:3" in checkpoint.tags
    assert checkpoint.content.splitlines()[0] == "会话检查点 seq 0-3（4 行）"
    assert "- user: 问1" in checkpoint.content
    assert "- assistant: 答2" in checkpoint.content


def test_only_new_evicted_range_is_written(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, ("问1", "答1"), ("问2", "答2"), ("问3", "答3"))
    memory = _memory()
    loop = _loop(memory, transcript)

    asyncio.run(_drain(loop.astream("问4", session_id="s1")))
    asyncio.run(_drain(loop.astream("问5", session_id="s1")))

    second = next(entry for entry in _checkpoints(memory) if entry.id == "context_checkpoint.s1.5")
    assert "seq_from:4" in second.tags  # 0–3 已写过，不重写
    assert "seq_to:5" in second.tags
    assert "- user: 问3" in second.content
    assert "- assistant: 答3" in second.content
    assert "问1" not in second.content


def test_replaying_same_window_writes_nothing_new(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, ("问1", "答1"), ("问2", "答2"), ("问3", "答3"))
    memory = _memory()
    loop = _loop(memory, transcript)
    plan = loop._window_plan(tiered=False)  # noqa: SLF001 — 幂等路径直测

    loop._checkpoint_evicted("s1", plan)  # noqa: SLF001 — 幂等路径直测
    before = len(_checkpoints(memory))
    loop._checkpoint_evicted("s1", plan)  # noqa: SLF001 — 幂等路径直测

    assert before == 1
    assert len(_checkpoints(memory)) == before


def test_no_eviction_writes_nothing(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, ("问1", "答1"))
    memory = _memory()
    loop = _loop(memory, transcript, history_turns=20)

    asyncio.run(_drain(loop.astream("问2", session_id="s1")))

    assert _checkpoints(memory) == []


def test_artifacts_aggregate_into_tags(tmp_path: Path) -> None:
    transcript = TranscriptStore(tmp_path / "messages.jsonl")
    transcript.append("s1", "user", "问1")
    transcript.append("s1", "assistant", "答1", artifacts=["a.py", "b.py"])
    transcript.append("s1", "user", "问2")
    transcript.append("s1", "assistant", "答2", artifacts=["a.py"])
    memory = _memory()
    loop = _loop(memory, transcript)

    asyncio.run(_drain(loop.astream("问3", session_id="s1")))

    (checkpoint,) = _checkpoints(memory)
    assert [tag for tag in checkpoint.tags if tag.startswith("artifact:")] == [
        "artifact:a.py",
        "artifact:b.py",
    ]


def test_no_artifacts_means_no_artifact_tags(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, ("问1", "答1"), ("问2", "答2"))
    memory = _memory()

    asyncio.run(_drain(_loop(memory, transcript).astream("问3", session_id="s1")))

    (checkpoint,) = _checkpoints(memory)
    assert not [tag for tag in checkpoint.tags if tag.startswith("artifact:")]


def test_checkpoint_content_is_redacted_and_bounded(tmp_path: Path) -> None:
    transcript = TranscriptStore(tmp_path / "messages.jsonl")
    transcript.append("s1", "user", f"我的密钥 {_SECRET}")
    transcript.append("s1", "assistant", "长" * 2000)
    transcript.append("s1", "user", "问2")
    transcript.append("s1", "assistant", "答2")
    memory = _memory()

    asyncio.run(_drain(_loop(memory, transcript).astream("问3", session_id="s1")))

    (checkpoint,) = _checkpoints(memory)
    assert _SECRET not in checkpoint.content
    assert REDACTED in checkpoint.content
    assert len(checkpoint.content) <= MAX_CHECKPOINT_CHARS
    assert all(
        len(line) <= MAX_CHECKPOINT_LINE_CHARS + len("- assistant: ")
        for line in checkpoint.content.splitlines()[1:]
    )


def test_checkpoint_write_is_reversible(tmp_path: Path) -> None:
    tracker = EffectTracker()
    memory = MemoryStore(effect_tracker=tracker)
    transcript = _transcript(tmp_path, ("问1", "答1"), ("问2", "答2"))

    asyncio.run(_drain(_loop(memory, transcript).astream("问3", session_id="s1")))
    assert _checkpoints(memory)

    report = tracker.rollback("context_checkpoint.s1.1")

    assert report.reverted
    assert _checkpoints(memory) == []


# ---- 门控与失败隔离 ----


def test_kill_switch_disables_checkpoint(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, ("问1", "答1"), ("问2", "答2"))
    memory = _memory()

    asyncio.run(_drain(_loop(memory, transcript, enabled=False).astream("问3", session_id="s1")))

    assert _checkpoints(memory) == []


def test_history_replay_disabled_means_no_checkpoint(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, ("问1", "答1"), ("问2", "答2"))
    memory = _memory()

    asyncio.run(_drain(_loop(memory, transcript, history_turns=0).astream("问3", session_id="s1")))

    assert _checkpoints(memory) == []


def test_empty_session_writes_nothing(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, ("问1", "答1"), ("问2", "答2"))
    memory = _memory()

    asyncio.run(_drain(_loop(memory, transcript).astream("问3")))

    assert _checkpoints(memory) == []


def test_without_memory_no_checkpoint_and_turn_completes(tmp_path: Path) -> None:
    transcript = _transcript(tmp_path, ("问1", "答1"), ("问2", "答2"))
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "完成"}),
        transcript=transcript,
        history_turns=1,
        context_checkpoint=True,
    )

    result = loop.run("问3", session_id="s1")

    assert result.reply == "完成"


def test_watermark_failure_degrades_without_breaking_turn(tmp_path: Path) -> None:
    class _BrokenWatermark(MemoryStore):
        def checkpoint_watermark(self, session_id: str) -> int:
            raise RuntimeError("boom")

    memory = _BrokenWatermark()
    transcript = _transcript(tmp_path, ("问1", "答1"), ("问2", "答2"))

    with pytest.warns(RuntimeWarning, match="检查点"):
        result = _loop(memory, transcript).run("问3", session_id="s1")

    assert result.reply == "完成"
    assert _checkpoints(memory) == []


def test_transcript_failure_degrades_without_breaking_turn(tmp_path: Path) -> None:
    class _BrokenEviction(TranscriptStore):
        def evicted_prefix(
            self,
            session_id: str,
            *,
            short_turns: int,
            mid_turns: int,
            short_tokens: int,
        ) -> tuple[int, list[dict[str, Any]]]:
            raise RuntimeError("boom")

    memory = _memory()
    transcript = _BrokenEviction(tmp_path / "messages.jsonl")
    transcript.append("s1", "user", "问1")
    transcript.append("s1", "assistant", "答1")
    transcript.append("s1", "user", "问2")
    transcript.append("s1", "assistant", "答2")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _loop(memory, transcript).run("问3", session_id="s1")

    assert result.reply == "完成"
    assert any("检查点" in str(item.message) for item in caught)
    assert _checkpoints(memory) == []


# ---- 纯函数 ----


def test_checkpoint_summary_renders_watermark_and_lines() -> None:
    rows: Sequence[dict[str, Any]] = [
        {"role": "user", "content": "第一问"},
        {"role": "assistant", "content": "第一答"},
    ]

    summary = checkpoint_summary(rows, seq_from=2, seq_to=3)

    assert summary.splitlines() == [
        "会话检查点 seq 2-3（2 行）",
        "- user: 第一问",
        "- assistant: 第一答",
    ]


def test_checkpoint_artifacts_is_deduped_and_bounded() -> None:
    rows: Sequence[dict[str, Any]] = [
        {"role": "assistant", "content": "", "artifacts": ["a.py", "b.py"]},
        {"role": "assistant", "content": "", "artifacts": ["a.py"]},
        {"role": "assistant", "content": ""},
        {"role": "assistant", "content": "", "artifacts": ["a.py", 42]},
    ]

    assert checkpoint_artifacts(rows) == ["a.py", "b.py"]
