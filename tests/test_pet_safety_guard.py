"""pet 安全中间件（pet-safety → loop 的 before 接缝，change 0081 / 账本 E25）。

中间件是 R12 的**执行点**：越界动作**不执行**、本轮**终止**（返回终止 Action，与 loop 既有
`decline()` 路径同构 —— 无需给 loop 加新语义）、并**通知主人**。会话状态不动（「暂停」= 本轮终止，
非 `suspend()`；生产无 `resume()` 调用方 ⇒ 转让行态即永久楔死）。
"""

from __future__ import annotations

from core.loop.protocol import Action, LoopContext
from core.pet.safety import SafetyBounds, build_safety_middleware


def test_terminal_action_passes_through() -> None:
    guard = build_safety_middleware(SafetyBounds())
    action = Action(args={"reply": "结束"})
    assert guard(LoopContext(), action) is action


def test_allowed_action_passes_through_unchanged() -> None:
    guard = build_safety_middleware(SafetyBounds(allowed_prefixes=["/work"]))
    action = Action(tool_id="tools.file_read", args={"path": "/work/a.txt"})
    assert guard(LoopContext(), action) is action


def test_out_of_bounds_action_blocked_and_owner_notified() -> None:
    sent: list[str] = []
    guard = build_safety_middleware(SafetyBounds(), notify=sent.append)
    blocked = guard(LoopContext(), Action(tool_id="tools.web_fetch", args={"url": "https://x"}))
    assert blocked is not None
    assert blocked.is_terminal
    assert "阻断" in blocked.args["reply"]
    assert len(sent) == 1
    assert "只读优先" in sent[0]


def test_blocked_without_notifier_still_blocks() -> None:
    guard = build_safety_middleware(SafetyBounds())
    blocked = guard(LoopContext(), Action(tool_id="tools.code_run", args={}))
    assert blocked is not None
    assert blocked.is_terminal


def test_radius_violation_reports_radius_reason() -> None:
    sent: list[str] = []
    guard = build_safety_middleware(SafetyBounds(allowed_prefixes=["/work"]), notify=sent.append)
    blocked = guard(LoopContext(), Action(tool_id="tools.file_read", args={"path": "/etc/passwd"}))
    assert blocked is not None
    assert blocked.is_terminal
    assert len(sent) == 1
    assert "爆炸半径" in sent[0]
