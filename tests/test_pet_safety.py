"""pet-safety 单元测试（只读优先、不可逆禁止、爆炸半径可控）。

词汇表已订正为**真实工具 id**（change 0081 / 账本 E25）：原默认集是发明词汇
（`file.write`/`git.push`/`rm`），与仓库真实 id（`tools.file_write`/`tools.code_run`…）一条都对不上
⇒ 即使接线也永不命中。只读判据亦由「`op.startswith("read")` 前缀启发式」改为**只读白名单**。
"""

from __future__ import annotations

from core.pet.safety import SafetyBounds


def test_read_only_blocks_non_allowlisted_tool() -> None:
    """白名单外的**非不可逆**工具（如出网）走「只读优先」分支 —— 不可逆工具另有分支（见下）。"""
    decision = SafetyBounds().check("tools.web_fetch", "/tmp/x")
    assert decision.blocked is True
    assert "只读优先" in decision.reason


def test_irreversible_blocked() -> None:
    decision = SafetyBounds(readonly=False).check("tools.file_write", "/etc/passwd")
    assert decision.blocked is True
    assert "不可逆" in decision.reason


def test_radius_out_of_bounds_blocked() -> None:
    safety = SafetyBounds(readonly=False, allowed_prefixes=["/home/harry/work"])
    decision = safety.check("tools.file_read", "/etc/passwd")
    assert decision.blocked is True
    assert "爆炸半径" in decision.reason


def test_read_within_bounds_allowed() -> None:
    safety = SafetyBounds(allowed_prefixes=["/home/harry/work"])
    decision = safety.check("tools.file_read", "/home/harry/work/x.txt")
    assert decision.blocked is False


def test_readonly_whitelisted_tool_without_target_allowed() -> None:
    """白名单内的真实只读工具 + 空 target ⇒ 放行（空 target 不误触发半径判定）。"""
    decision = SafetyBounds(allowed_prefixes=["/home/harry/work"]).check("tools.file_read")
    assert decision.blocked is False


def test_unknown_tool_blocks_when_readonly() -> None:
    """白名单外的一切（含拼错/未知工具）在只读口径下 fail-closed 阻断。"""
    assert SafetyBounds().check("tools.made_up", "/tmp/x").blocked is True
