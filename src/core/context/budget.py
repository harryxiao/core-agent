"""预算管理（BudgetManager）。

按优先级裁剪上下文至 token 预算内：宪章/未决事项/验收标准必保，低相关度
事实/技能优先裁剪；连必保内容都超预算则抛 BUDGET_EXCEEDED。

对应接口：doc/03-interfaces/context-interface.md §5
"""

from __future__ import annotations

from core.tokens import estimate_tokens

from .errors import ContextError, ContextErrorCode
from .models import ContextPack


class BudgetManager:
    """上下文预算控制：超预算裁剪低相关度内容，必保项优先。"""

    def enforce(self, pack: ContextPack, budget: int) -> ContextPack:
        """裁剪至预算内，返回（可能被裁剪的）pack；必保项超预算抛 BUDGET_EXCEEDED。"""
        pack.token_budget = budget
        pack.token_used = self._measure(pack)
        if pack.token_used <= budget:
            return pack
        mandatory = self._mandatory_tokens(pack)
        if mandatory > budget:
            raise ContextError(
                ContextErrorCode.BUDGET_EXCEEDED, "必保内容（宪章/未决事项）已超预算"
            )
        pack.facts = self._trim(pack.facts, budget - mandatory)
        pack.token_used = self._measure(pack)
        return pack

    def _measure(self, pack: ContextPack) -> int:
        total = estimate_tokens(pack.task) + estimate_tokens(pack.stage)
        total += sum(estimate_tokens(str(c)) for c in pack.constitution)
        total += sum(estimate_tokens(str(p)) for p in pack.pending)
        total += sum(estimate_tokens(str(f)) for f in pack.facts)
        return total

    def _mandatory_tokens(self, pack: ContextPack) -> int:
        total = estimate_tokens(pack.task) + estimate_tokens(pack.stage)
        total += sum(estimate_tokens(str(c)) for c in pack.constitution)
        total += sum(estimate_tokens(str(p)) for p in pack.pending)
        return total

    @staticmethod
    def _trim(items: list[dict[str, str]], budget: int) -> list[dict[str, str]]:
        """按序保留可容纳项，**跳过**放不下的项（不掐断后续）。

        入参按相关度降序（见 ``DynamicAssembler``）：单项超预算只裁该项本身，
        不阻塞其后更小的低相关项，避免头部大项造成整体饥饿。
        """
        kept: list[dict[str, str]] = []
        used = 0
        for item in items:
            cost = estimate_tokens(str(item))
            if used + cost > budget:
                continue
            kept.append(item)
            used += cost
        return kept
