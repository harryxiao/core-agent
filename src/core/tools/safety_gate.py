"""确认门（tool-use）。

按工具可逆性与 coeffect 副作用声明判定是否需要人工确认：只读 / 可逆写
自动放行；不可逆写 或 高风险 coeffect（secret / external / 出站网络）需确认。
默认门无人工通道，故「需确认」由 Provider 映射为 IRREVERSIBLE_BLOCKED。

对应接口：doc/03-interfaces/tool-use-interface.md §4
"""

from __future__ import annotations

from typing import Any

from .models import GateDecision

_SECRET_PREFIX = "secret:"
_NETWORK_PREFIX = "network:"
_EXTERNAL = "external"


class SafetyGate:
    """默认确认门：只读 / 可逆写 auto，不可逆写 / 高风险 confirm。"""

    def confirm(
        self,
        tool_id: str,
        args: dict[str, Any],
        coeffects: list[str],
        reversible: bool,
    ) -> GateDecision:
        if self._is_high_risk(coeffects):
            return GateDecision("confirm", f"工具 {tool_id} 高风险 coeffect，需人工确认")
        if self._is_write(coeffects) and not reversible:
            return GateDecision("confirm", f"工具 {tool_id} 不可逆写，需人工确认")
        return GateDecision("auto", "只读或可逆，自动放行")

    @staticmethod
    def _is_high_risk(coeffects: list[str]) -> bool:
        return any(
            c == _EXTERNAL or c.startswith(_SECRET_PREFIX) or c.startswith(_NETWORK_PREFIX)
            for c in coeffects
        )

    @staticmethod
    def _is_write(coeffects: list[str]) -> bool:
        return any("write" in c for c in coeffects)
