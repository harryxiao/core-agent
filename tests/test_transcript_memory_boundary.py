"""反例守门：转录不是记忆层级（change 0115）。

钉住规格 `memory/spec.md`「对话转录持久化（非记忆层级）」的可执行边界：
转录是**独立的对话日志**，不是任何 L0–L4 条目 —— 追加转录 SHALL NOT 使
``MemoryStore.read`` 多出条目，``MemoryStore.write`` 也 SHALL NOT 产出转录。
"""

from __future__ import annotations

from pathlib import Path

from core.memory import MemoryEntry, MemoryStore, TranscriptStore


def test_transcript_never_returned_by_memory_read(tmp_path: Path) -> None:
    memory = MemoryStore()
    store = TranscriptStore(tmp_path / "messages.jsonl")
    store.append("s1", "user", "部署方案 用蓝绿发布")
    store.append("s1", "assistant", "好的")

    # 无论是否开本会话过滤，检索面都看不到转录（转录不是记忆条目）
    assert memory.read("部署方案 蓝绿发布", 2048, session_id="s1") == []
    assert memory.read("部署方案 蓝绿发布", 2048) == []


def test_memory_write_never_reaches_transcript(tmp_path: Path) -> None:
    memory = MemoryStore()
    store = TranscriptStore(tmp_path / "messages.jsonl")
    memory.write(
        "L2",
        MemoryEntry(
            id="e1",
            layer="L2",
            content="沉淀的事实",
            tags=["loop"],
            source="loop",
            trace_id="t1",
            session_id="s1",
        ),
    )

    assert store.read("s1") == []
    assert store.summaries() == {}
