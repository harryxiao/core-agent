"""宠物安全边界（pet-safety）。

只读优先、不可逆操作禁止、爆炸半径可控、越界即阻断（R12）；实现
core.pet.core.SafetyLayer 安全边界层。越界返回 SafetyDecision（阻断是决策非错误），
由安全中间件据此短路本轮并通知主人（change 0081 / 账本 E25）。

词汇表 = **真实工具 id**（如 `tools.file_write` / `tools.code_run`）：原默认集是发明词汇
（`file.write` / `git.push` / `rm`），与仓库真实 id 一条都对不上 ⇒ 接线也永不命中；
只读判据亦由「`op.startswith("read")` 前缀启发式」改为**只读白名单**（真实 id 无 `read` 前缀）。

对应接口：doc/03-interfaces/pet-mode-interface.md（安全边界与受限探索工具集）
"""

from __future__ import annotations

from core.pet.core import SafetyDecision

# 默认不可逆操作集合（真实工具 id：写 / 改 / 派生进程 / 装卸）。
_DEFAULT_IRREVERSIBLE = frozenset(
    {
        "tools.file_write",
        "tools.file_patch",
        "tools.code_run",
        "tools.install",
        "tools.uninstall",
    }
)

# 默认只读白名单（真实只读工具 id）：`readonly=True` 时白名单外一律阻断（fail-closed）。
_DEFAULT_READONLY = frozenset({"tools.file_read"})


class SafetyBounds:
    """安全边界：只读优先 + 不可逆禁止 + 爆炸半径可控（真实工具 id 口径）。"""

    def __init__(
        self,
        *,
        readonly: bool = True,
        allowed_prefixes: list[str] | None = None,
        irreversible_ops: set[str] | None = None,
        readonly_ops: set[str] | None = None,
    ) -> None:
        self._readonly = readonly
        self._prefixes: list[str] = allowed_prefixes if allowed_prefixes is not None else []
        self._irreversible: set[str] = (
            set(irreversible_ops) if irreversible_ops is not None else set(_DEFAULT_IRREVERSIBLE)
        )
        self._readonly_ops: set[str] = (
            set(readonly_ops) if readonly_ops is not None else set(_DEFAULT_READONLY)
        )

    def check(self, op: str, target: str = "") -> SafetyDecision:
        """越界/不可逆操作被阻断，返回 (blocked, reason)。

        ``op`` 为**真实工具 id**；``target`` 为空（该工具无路径类参数）时**不做**半径判定。
        判定顺序：不可逆 → 只读白名单 → 爆炸半径。
        """
        if op in self._irreversible:
            return SafetyDecision(blocked=True, reason=f"不可逆操作禁止: {op}")
        if self._readonly and op not in self._readonly_ops:
            return SafetyDecision(blocked=True, reason=f"只读优先，白名单外操作越界: {op}")
        if self._prefixes and target and not any(target.startswith(p) for p in self._prefixes):
            return SafetyDecision(blocked=True, reason=f"爆炸半径越界: {target}")
        return SafetyDecision(blocked=False)
