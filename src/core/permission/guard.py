"""权限守卫（PermissionGuard）：把 :class:`PermissionModeGate` 适配为 loop 确认门。

替代 loop / tool-use 默认 :class:`SafetyGate`：按 config.permission.mode 四档 +
风险分级判定；不可逆写 / 高危动作过审批门（confirm），read-only / high-risk-block
模式直接 deny；注入 judgment :class:`Guardrail` 时，分级放行前加 noul 二次校验。

对应接口：doc/03-interfaces/permission-interface.md §2（PermissionModeGate 的 loop 适配）
"""

from __future__ import annotations

from typing import Any, cast

from core.judgment import DecisionResult, Guardrail
from core.tools import GateDecision, SafetyGate

from .errors import AccessControlError
from .models import Decision, PermissionMode
from .policy import PermissionModeGate


class PermissionGuard(SafetyGate):
    """loop 确认门适配器：confirm() → 权限门 authorize()。"""

    def __init__(
        self,
        mode: PermissionMode | str = PermissionMode.INTERACTIVE,
        *,
        guardrail: Guardrail | None = None,
        allowed_coeffects: frozenset[str] | None = None,
    ) -> None:
        self._gate = PermissionModeGate(
            mode if isinstance(mode, PermissionMode) else PermissionMode.from_config(mode),
            allowed_coeffects=allowed_coeffects,
        )
        self._mode = self._gate.mode  # 模式构造后不变（无 setter），记下供 confirm 分支读取
        self._guardrail = guardrail

    def confirm(
        self,
        tool_id: str,
        args: dict[str, Any],
        coeffects: list[str],
        reversible: bool,
    ) -> GateDecision:
        target = str(args.get("path") or tool_id)
        try:
            decision = self._gate.authorize(tool_id, target, coeffects)
        except AccessControlError as exc:
            return GateDecision("deny", str(exc))
        if not decision.allowed:
            return _to_gate(decision)
        if self._guardrail is not None:
            verdict = self._guardrail.check(
                {"op": tool_id, "target": target, "coeffects": coeffects},
                {"args": args},
            )
            if not self._noul_true(verdict):
                return GateDecision("deny", f"judgment 守卫拦截: {tool_id}")
        # auto-approve 档无人值守：不因「不可逆」进 confirm（guardrail 已在上面拦住）
        if (
            self._is_write(coeffects)
            and not reversible
            and self._mode is not PermissionMode.AUTO_APPROVE
        ):
            return GateDecision("confirm", f"工具 {tool_id} 不可逆写，需人工审批")
        return GateDecision("auto", decision.reason)

    @staticmethod
    def _is_write(coeffects: list[str]) -> bool:
        return any("write" in c for c in coeffects)

    @staticmethod
    def _noul_true(verdict: DecisionResult) -> bool:
        if verdict.fallback:
            return True  # 回退（无 JEV / 无把握）不拦截，策略门兜底
        answer = verdict.answers.get("noul")
        if not isinstance(answer, dict):
            return True
        return bool(cast(dict[str, Any], answer).get("noul"))


def _to_gate(decision: Decision) -> GateDecision:
    if decision.allowed:
        return GateDecision("auto", decision.reason)
    if decision.approval_required:
        return GateDecision("confirm", decision.reason)
    return GateDecision("deny", decision.reason)
