"""本轮 L2 记忆沉淀：轨迹条目 **+** 行动序列条目（change 0173 / ADR-0164 / 台账 E110）。

取证（change 0173）：抽取器对**每条** L2 条目只取前 `_MAX_ENTRY_CHARS`(400) 字符入 prompt，
而探到的 **24/24** 条 keyfact 实体**全部**产自轨迹条目的**散文**（`round N ok` + 回复）
⇒ 行动序列若插进既有条目开头会把那段散文顶出窗口。故行动序列**另立一条**条目
（两条各占一窗），轨迹条目内容**逐字不变**。
"""

from __future__ import annotations

import json

from core.loop import DefaultLoop, LoopContext
from core.loop.default import _MAX_MEMORY_ENTRY, _action_steps
from core.memory import REDACTED, MemoryStore


def _ctx(*messages: object) -> LoopContext:
    return LoopContext(messages=list(messages))


def _action(tool_id: str, args: dict[str, object]) -> dict[str, str]:
    return {"role": "assistant", "content": json.dumps({"tool_id": tool_id, "args": args})}


def _observation(data: object) -> dict[str, str]:
    return {"role": "tool", "content": json.dumps({"data": data})}


def _contents(store: MemoryStore) -> dict[str, str]:
    return {str(entry.id): entry.content for entry in store.audit()}


def _echo_ctx() -> LoopContext:
    return _ctx(
        {"role": "user", "content": "跑个回显"},
        _action("tools.echo", {"text": "中间结论"}),
        _observation("echo:中间结论"),
    )


def test_action_sequence_lands_as_separate_entry() -> None:
    """有工具调用 ⇒ 轨迹条目 + 行动序列条目**并存**，轨迹条目内容逐字不变。"""
    store = MemoryStore()

    DefaultLoop(memory=store).remember(
        "t1", [{"round": 1, "ok": True}, {"reply": "已回显"}], steps=_action_steps(_echo_ctx())
    )

    assert _contents(store) == {
        "loop.t1": "round 1 ok\n已回显",
        "loop.steps.t1": "tools.echo（text: 中间结论） → echo:中间结论",
    }


def test_sequence_entry_shares_trace_and_session() -> None:
    """行动序列条目与轨迹条目同 `trace_id` / 同 `session_id` / 同层（回滚与归组口径一致）。"""
    store = MemoryStore()
    DefaultLoop(memory=store).remember("t2", [{"reply": "ok"}], session_id="s1", steps=["a → b"])

    seq = next(entry for entry in store.audit() if entry.id == "loop.steps.t2")
    assert seq.layer == "L2"
    assert seq.trace_id == "t2"
    assert seq.session_id == "s1"
    assert seq.source == "loop"


def test_reply_only_turn_does_not_add_sequence_entry() -> None:
    """纯文字回复轮（`_action_steps` 为空）⇒ 只沉淀轨迹条目（无行动不记忆）。"""
    store = MemoryStore()

    DefaultLoop(memory=store).remember(
        "t3", [{"reply": "你好"}], steps=_action_steps(_ctx({"role": "user", "content": "你好"}))
    )

    assert set(_contents(store)) == {"loop.t3"}


def test_default_steps_keeps_trajectory_entry_only() -> None:
    """`steps` 缺省（旧调用形态）⇒ 行为与变更前**逐字一致**（向后兼容）。"""
    store = MemoryStore()

    DefaultLoop(memory=store).remember("t4", [{"reply": "结论"}])

    assert _contents(store) == {"loop.t4": "结论"}


def test_sequence_entry_redacts_secret_substrings() -> None:
    """行动序列含密钥形态串 ⇒ 该子串脱敏（工具名 / 结构保留），条目**不含**明文。"""
    store = MemoryStore()
    ctx = _ctx(
        {"role": "user", "content": "跑"},
        _action("code_run", {"script": "echo"}),
        _observation("token: sk-abcdefgh12345678"),
    )

    DefaultLoop(memory=store).remember("t5", [{"reply": "ok"}], steps=_action_steps(ctx))

    content = _contents(store)["loop.steps.t5"]
    assert "sk-abcdefgh12345678" not in content
    assert REDACTED in content
    assert content.startswith("code_run（")


def test_trajectory_entry_redacts_secret_substrings() -> None:
    """轨迹条目写入前整条脱敏；未命中密钥形态的正文与结构逐字不变（change 0241）。"""
    store = MemoryStore()

    DefaultLoop(memory=store).remember(
        "t3", [{"round": 1, "ok": True}, {"reply": "api_key: sk-abcdefghijklmnop"}]
    )

    content = _contents(store)["loop.t3"]
    assert content.startswith("round 1 ok\n"), "轮次/成败结构保留"
    assert "sk-abcdefghijklmnop" not in content, "明文密钥不得落库"
    assert "<redacted>" in content


def test_sequence_entry_is_bounded() -> None:
    """超长行动序列 ⇒ 条目长度不超过 `_MAX_MEMORY_ENTRY`（token 有界）。"""
    store = MemoryStore()
    steps = [f"tools.echo（text: {i}） → {'x' * 200}" for i in range(40)]

    DefaultLoop(memory=store).remember("t6", [{"reply": "ok"}], steps=steps)

    assert len(_contents(store)["loop.steps.t6"]) <= _MAX_MEMORY_ENTRY
