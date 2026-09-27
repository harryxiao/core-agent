"""pet-safety 单元测试（只读优先、不可逆禁止、爆炸半径可控）。"""

from __future__ import annotations

from core.pet_safety import SafetyBounds


def test_read_only_blocks_write() -> None:
    decision = SafetyBounds().check("file.edit", "/tmp/x")
    assert decision.blocked is True
    assert "只读优先" in decision.reason


def test_irreversible_blocked() -> None:
    decision = SafetyBounds(readonly=False).check("rm", "/etc/passwd")
    assert decision.blocked is True
    assert "不可逆" in decision.reason


def test_radius_out_of_bounds_blocked() -> None:
    safety = SafetyBounds(readonly=False, allowed_prefixes=["/home/harry/work"])
    decision = safety.check("read", "/etc/passwd")
    assert decision.blocked is True
    assert "爆炸半径" in decision.reason


def test_read_within_bounds_allowed() -> None:
    safety = SafetyBounds(allowed_prefixes=["/home/harry/work"])
    decision = safety.check("read", "/home/harry/work/x.txt")
    assert decision.blocked is False
