"""权限分级策略引擎（permission）。

按操作 / 目标 / coeffect 关键词分级：删杀 / 密钥 / 出站网络 → HIGH_RISK，
写 → DATA_EDIT，读 → READ，无法归类 → HIGH_RISK（deny-by-default）。

对应接口：doc/03-interfaces/permission-interface.md §2
"""

from __future__ import annotations

from .models import Decision, RiskLevel

_HIGH_RISK_TOKENS = (
    "delete",
    "rm",
    "kill",
    "exec",
    "shell",
    "install",
    "purge",
    "drop",
    "terminate",
    "sudo",
    "admin",
)
_WRITE_TOKENS = (
    "write",
    "edit",
    "update",
    "patch",
    "put",
    "post",
    "create",
    "set",
    "append",
    "modify",
    "grant",
    "revoke",
)
_READ_TOKENS = ("read", "get", "list", "search", "query", "ls", "cat", "view", "show", "stat")


class PolicyEngine:
    """风险分级与授权。"""

    def classify(self, op: str, target: str, coeffect: list[str]) -> RiskLevel:
        op_l = op.lower()
        target_l = target.lower()
        if any(tok in op_l or tok in target_l for tok in _HIGH_RISK_TOKENS):
            return RiskLevel.HIGH_RISK
        if any(
            c.startswith("secret:") or c.startswith("network:") or c == "external" for c in coeffect
        ):
            return RiskLevel.HIGH_RISK
        if any(tok in op_l for tok in _WRITE_TOKENS):
            return RiskLevel.DATA_EDIT
        if any(tok in op_l for tok in _READ_TOKENS):
            return RiskLevel.READ
        return RiskLevel.HIGH_RISK  # 无法归类 → deny-by-default

    def authorize(self, op: str, target: str, risk: RiskLevel) -> Decision:
        if risk == RiskLevel.HIGH_RISK:
            return Decision(
                False, f"高危操作 {op} 作用于 {target}，需人工审批", approval_required=True
            )
        return Decision(True, f"{risk.value} 操作放行")
