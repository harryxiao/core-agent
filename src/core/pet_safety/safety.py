"""宠物安全边界（pet-safety）。

只读优先、不可逆操作禁止、爆炸半径可控、越界即阻断（R12）；实现
pet_core.SafetyLayer 安全边界层。越界返回 SafetyDecision（阻断是决策非
错误），PetSession 据此暂停并通知主人。

对应接口：doc/03-interfaces/pet-mode-interface.md §1（安全边界层）
"""

from __future__ import annotations

from core.pet_core import SafetyDecision

# 默认不可逆操作集合。
_DEFAULT_IRREVERSIBLE = {"file.write", "file.patch", "git.push", "rm"}


class SafetyBounds:
    """安全边界：只读优先 + 不可逆禁止 + 爆炸半径可控。"""

    def __init__(
        self,
        *,
        readonly: bool = True,
        allowed_prefixes: list[str] | None = None,
        irreversible_ops: set[str] | None = None,
    ) -> None:
        self._readonly = readonly
        self._prefixes: list[str] = allowed_prefixes if allowed_prefixes is not None else []
        self._irreversible: set[str] = (
            irreversible_ops if irreversible_ops is not None else _DEFAULT_IRREVERSIBLE
        )

    def check(self, op: str, target: str) -> SafetyDecision:
        """越界/不可逆操作被阻断，返回 (blocked, reason)。"""
        if op in self._irreversible:
            return SafetyDecision(blocked=True, reason=f"不可逆操作禁止: {op}")
        if self._readonly and not op.startswith("read"):
            return SafetyDecision(blocked=True, reason=f"只读优先，写操作越界: {op}")
        if self._prefixes and not any(target.startswith(prefix) for prefix in self._prefixes):
            return SafetyDecision(blocked=True, reason=f"爆炸半径越界: {target}")
        return SafetyDecision(blocked=False)
