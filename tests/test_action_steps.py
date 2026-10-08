"""`_action_steps` 可读渲染（change `0171` / ADR-0162 / 台账 E108）。

逐轮写回（notes）与 SOP 提炼共用 loop 收尾钩子交付的行动序列。旧实现把 ReAct 消息**原文**
（`json.dumps` 的 `{"tool_id":…}` / `{"data":…}`）逐条落成 ``role: content``，既不可读又无界。
本测守护新契约：人类可读行 + 有界 + 纯文字回复轮为空（供写回侧有意义闸门判定）。
"""

from __future__ import annotations

import json

from core.loop import LoopContext
from core.loop.default import _MAX_STEP_LINE, _MAX_STEP_VALUE, _action_steps


def _ctx(*messages: object) -> LoopContext:
    return LoopContext(messages=list(messages))


def _action(tool_id: str, args: dict[str, object]) -> dict[str, str]:
    return {"role": "assistant", "content": json.dumps({"tool_id": tool_id, "args": args})}


def _observation(data: object) -> dict[str, str]:
    return {"role": "tool", "content": json.dumps({"data": data})}


def _error(error: str) -> dict[str, str]:
    return {"role": "tool", "content": json.dumps({"error": error})}


def test_action_steps_renders_readable_line() -> None:
    ctx = _ctx(
        {"role": "user", "content": "跑个回显"},
        _action("tools.echo", {"text": "中间结论"}),
        _observation("echo:中间结论"),
    )
    assert _action_steps(ctx) == ["tools.echo（text: 中间结论） → echo:中间结论"]


def test_action_steps_has_no_raw_json_dump() -> None:
    ctx = _ctx(
        {"role": "user", "content": "任务"},
        _action("file_read", {"path": "src/core/ui/repl.py"}),
        _observation({"content": "整篇文件正文", "bytes": 4096}),
    )
    joined = "\n".join(_action_steps(ctx))
    for marker in ('{"tool_id"', '{"data"', '"args"', "assistant:", "tool:"):
        assert marker not in joined, f"正文不得落 ReAct 消息原文/角色前缀：{marker}"
    assert "file_read（path: src/core/ui/repl.py）" in joined


def test_action_steps_empty_for_reply_only_turn() -> None:
    # 纯文字回复轮：终止动作不产生行动消息（_record_observation 对 is_terminal 早退）。
    assert _action_steps(_ctx({"role": "user", "content": "你好"})) == []


def test_action_steps_bounds_long_arg_and_output() -> None:
    huge_arg = "x" * 5000
    huge_out = "y" * 5000
    ctx = _ctx(
        {"role": "user", "content": "任务"},
        _action("file_write", {"path": "a.py", "content": huge_arg}),
        _observation(huge_out),
    )
    steps = _action_steps(ctx)
    assert len(steps) == 1
    line = steps[0]
    assert len(line) <= _MAX_STEP_LINE, "整行有界"
    assert huge_arg not in line, "参数值有界（不 dump 正文）"
    assert huge_out not in line, "结果节选有界（不 dump 整篇输出）"
    assert "…" in line, "截断留痕"


def test_action_steps_reports_container_arg_by_type_and_size() -> None:
    ctx = _ctx(
        {"role": "user", "content": "任务"},
        _action("code_run", {"script": "print(1)", "env": {"A": "1", "B": "2"}}),
        _observation("1"),
    )
    line = _action_steps(ctx)[0]
    assert "env: <dict len=2>" in line, "容器型参数只报类型与规模"
    assert '"A"' not in line, "容器的键值不 dump"


def test_action_steps_marks_tool_error() -> None:
    ctx = _ctx(
        {"role": "user", "content": "任务"},
        _action("file_read", {"path": "missing.py"}),
        _error("NOT_FOUND"),
    )
    assert _action_steps(ctx) == ["file_read（path: missing.py） → 错误：NOT_FOUND"]


def test_action_steps_skips_message_without_action_shape() -> None:
    # 非 {"tool_id": str} 形态的助手消息不产行（畸形输入静默跳过，不崩）。
    ctx = _ctx(
        {"role": "user", "content": "任务"},
        {"role": "assistant", "content": "just text, not an action"},
    )
    assert _action_steps(ctx) == []


def test_action_steps_value_truncation_uses_max_step_value() -> None:
    long_str = "z" * (_MAX_STEP_VALUE + 10)
    ctx = _ctx(
        {"role": "user", "content": "任务"},
        _action("tools.echo", {"text": long_str}),
        _observation("ok"),
    )
    line = _action_steps(ctx)[0]
    assert long_str not in line
    assert line.startswith(f"tools.echo（text: {'z' * _MAX_STEP_VALUE}…）")
