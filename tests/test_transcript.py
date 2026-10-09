"""对话转录存储（TranscriptStore）：按轮追加 + 按会话读取 + 派生摘要。

对应规格：`doc/openspec/specs/memory/spec.md`「对话转录持久化（非记忆层级）」。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.memory import TranscriptStore


def _store(tmp_path: Path) -> TranscriptStore:
    return TranscriptStore(tmp_path / "messages.jsonl")


# ---- 追加 / 读取 ----


def test_append_then_read_roundtrip() -> None:
    store = TranscriptStore()
    store.append("s1", "user", "你好")
    store.append("s1", "assistant", "在的")

    entries = store.read("s1")

    assert [e["role"] for e in entries] == ["user", "assistant"]
    assert [e["content"] for e in entries] == ["你好", "在的"]
    assert all(e["session_id"] == "s1" for e in entries)
    assert entries[0]["created_at"] <= entries[1]["created_at"]


def test_cross_instance_visible(tmp_path: Path) -> None:
    """落盘后另一实例（模拟另一进程）读得到。"""
    path = tmp_path / "messages.jsonl"
    TranscriptStore(path).append("s1", "user", "落盘")

    assert [e["content"] for e in TranscriptStore(path).read("s1")] == ["落盘"]


def test_read_is_scoped_by_session(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.append("a", "user", "A 的问题")
    store.append("b", "user", "B 的问题")

    assert [e["content"] for e in store.read("a")] == ["A 的问题"]
    # 反例守门：B 读不到 A
    assert [e["content"] for e in store.read("b")] == ["B 的问题"]


def test_unaffiliated_append_is_noop(tmp_path: Path) -> None:
    """空标识 = 未归属：不落盘（否则未归属轮会挤进同一个 "" 桶变成幻影会话）。"""
    store = _store(tmp_path)
    store.append("", "user", "未归属")

    assert store.read("") == []
    assert store.summaries() == {}
    assert not (tmp_path / "messages.jsonl").exists()


# ---- tail：最近 N 轮 + token 切片 ----


def test_tail_limits_turns() -> None:
    store = TranscriptStore()
    for i in range(5):
        store.append("s", "user", f"q{i}")
        store.append("s", "assistant", f"a{i}")

    assert [e["content"] for e in store.tail("s", 2)] == ["q3", "a3", "q4", "a4"]


def test_tail_zero_turns_is_empty() -> None:
    store = TranscriptStore()
    store.append("s", "user", "q")
    assert store.tail("s", 0) == []


def test_tail_more_turns_than_available() -> None:
    store = TranscriptStore()
    store.append("s", "user", "q0")
    store.append("s", "assistant", "a0")

    assert [e["content"] for e in store.tail("s", 99)] == ["q0", "a0"]


def test_tail_keeps_trailing_unanswered_user() -> None:
    """尾部提问尚未答复（如落盘后回复前中断）时，该 user 行仍被保留。"""
    store = TranscriptStore()
    store.append("s", "user", "q0")
    store.append("s", "assistant", "a0")
    store.append("s", "user", "q1")

    assert [e["content"] for e in store.tail("s", 5)] == ["q0", "a0", "q1"]


def test_tail_token_bound_drops_oldest_lines() -> None:
    store = TranscriptStore()
    for i in range(5):
        store.append("s", "user", chr(ord("a") + i) * 160)  # 40 token
        store.append("s", "assistant", chr(ord("A") + i) * 160)  # 40 token

    tail = store.tail("s", 99, max_tokens=100)

    assert [e["content"] for e in tail] == ["e" * 160, "E" * 160]


def test_tail_token_bound_never_starts_mid_round() -> None:
    """token 切片截在轮中间时，丢弃开头的孤儿 assistant 行（其提问已不在）。"""
    store = TranscriptStore()
    store.append("s", "user", "a" * 40)  # 10 token
    store.append("s", "assistant", "b" * 40)  # 10 token
    store.append("s", "user", "c" * 40)  # 10 token
    store.append("s", "assistant", "d" * 40)  # 10 token

    # 35 token：末三行（b/c/d）在界内，但 b 是被截断轮的答复 ⇒ 结果自 c 起
    assert [e["content"] for e in store.tail("s", 99, max_tokens=35)] == ["c" * 40, "d" * 40]


# ---- window：三层滑窗的短/中带切分（change 0178 / ADR-0169） ----


def _eight_turns() -> TranscriptStore:
    store = TranscriptStore()
    for i in range(8):
        store.append("s", "user", f"q{i}")
        store.append("s", "assistant", f"a{i}")
    return store


def test_window_splits_short_and_mid_bands() -> None:
    """短带 = 末 `short_turns` 轮、中带 = 其前 `mid_turns` 轮，两带**不重叠**。"""
    short, mid = _eight_turns().window("s", short_turns=2, mid_turns=3, short_tokens=0)

    assert [e["content"] for e in short] == ["q6", "a6", "q7", "a7"]
    assert [e["content"] for e in mid] == ["q3", "a3", "q4", "a4", "q5", "a5"]
    assert {e["content"] for e in short}.isdisjoint({e["content"] for e in mid})


def test_window_short_band_truncated_by_short_tokens() -> None:
    """短带按 `short_tokens` 从新到旧截断（丢最旧），中带**不**截断。"""
    store = TranscriptStore()
    for i in range(5):
        store.append("s", "user", chr(ord("a") + i) * 160)  # 40 token
        store.append("s", "assistant", chr(ord("A") + i) * 160)

    short, _ = store.window("s", short_turns=5, mid_turns=0, short_tokens=100)

    assert [e["content"] for e in short] == ["e" * 160, "E" * 160]


def test_window_short_band_drops_leading_orphan_assistant() -> None:
    """短带 token 切片截在轮中间 ⇒ 丢弃开头的孤儿 assistant（承 `tail` 语义）。"""
    store = TranscriptStore()
    store.append("s", "user", "a" * 40)  # 10 token
    store.append("s", "assistant", "b" * 40)
    store.append("s", "user", "c" * 40)
    store.append("s", "assistant", "d" * 40)

    short, _ = store.window("s", short_turns=99, mid_turns=0, short_tokens=35)

    assert [e["content"] for e in short] == ["c" * 40, "d" * 40]


def test_window_insufficient_turns_leaves_mid_empty() -> None:
    """会话轮数不足 ⇒ 短带吃满、中带为空（无更旧内容可摘）。"""
    store = TranscriptStore()
    store.append("s", "user", "q0")
    store.append("s", "assistant", "a0")

    short, mid = store.window("s", short_turns=10, mid_turns=6, short_tokens=0)

    assert [e["content"] for e in short] == ["q0", "a0"]
    assert mid == []


@pytest.mark.parametrize("short_turns", [0, -1])
def test_window_zero_or_negative_short_turns_returns_empty(short_turns: int) -> None:
    assert _eight_turns().window("s", short_turns=short_turns, mid_turns=3, short_tokens=0) == (
        [],
        [],
    )


def test_window_untiered_equivalent_to_tail() -> None:
    """非分层等价锚：`window(N, 0, B)` ≡ `tail(N, max_tokens=B)`（同一 token 截断语义）。"""
    store = _eight_turns()

    short, mid = store.window("s", short_turns=3, mid_turns=0, short_tokens=1000)
    tail = store.tail("s", 3, max_tokens=1000)

    assert short == tail
    assert mid == []


# ---- 降级 ----


def test_missing_file_reads_as_empty(tmp_path: Path) -> None:
    assert TranscriptStore(tmp_path / "nope.jsonl").read("s") == []


def test_bad_lines_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "messages.jsonl"
    good = json.dumps({"session_id": "s", "role": "user", "content": "ok", "created_at": 1.0})
    path.write_text(f"{good}\nnot json\n\n[1, 2]\n", encoding="utf-8")

    assert [e["content"] for e in TranscriptStore(path).read("s")] == ["ok"]


# ---- 派生摘要（会话列表的读模型） ----


def test_summaries_title_and_updated_at() -> None:
    store = TranscriptStore()
    store.append("s1", "user", "第一个问题", created_at=10.0)
    store.append("s1", "assistant", "回答", created_at=100.0)
    store.append("s2", "user", "第二个问题", created_at=200.0)

    summaries = store.summaries()

    assert summaries["s1"] == {"title": "第一个问题", "updated_at": 100.0}
    assert summaries["s2"]["title"] == "第二个问题"


def test_summaries_title_from_first_user_message() -> None:
    """标题取**首条用户消息**：开场 assistant 行不作标题；换行压平、超长截断。"""
    store = TranscriptStore()
    store.append("s", "assistant", "开场白")
    store.append("s", "user", "标题\n带换行" + "长" * 40)
    store.append("s", "user", "第二问")

    title = store.summaries()["s"]["title"]

    assert title == "标题 带换行" + "长" * 24 + "…"  # 30 字 + 省略号


def test_summaries_skips_unaffiliated_session() -> None:
    store = TranscriptStore()
    store.append("", "user", "未归属")
    assert store.summaries() == {}
