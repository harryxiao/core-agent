"""权限分级策略引擎（permission）。

按操作 / 目标 / coeffect 关键词分级：删杀 / 密钥 / 出站网络 → HIGH_RISK，
写 → DATA_EDIT，读 → READ，无法归类 → HIGH_RISK（deny-by-default）。

对应接口：doc/03-interfaces/permission-interface.md §2
"""

from __future__ import annotations

from .errors import AccessControlError, PermissionErrorCode
from .models import Decision, PermissionMode, RiskLevel

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
_READ_TOKENS = ("read", "get", "list", "search", "query", "cat", "view", "show", "stat")
# 委托类 coeffect 的**字面量**只读豁免：SHALL NOT 放宽为 "agent:" 前缀，
# 否则将来任何 `agent:*` coeffect 会静默变只读（同 change 0095 的「按词元非子串」口径）。
_DELEGATE_COEFFECT = "agent:delegate"


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
        if _DELEGATE_COEFFECT in coeffect:  # list 元素等值匹配，非子串
            return RiskLevel.READ
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


class PermissionModeGate:
    """权限模式门：四档启动开关，覆盖 :class:`PolicyEngine` 的默认授权。

    - read-only：拒绝写 / 编辑 / 删除类操作（``PERMISSION_DENIED``）。
    - interactive：高危走人工审批（默认行为）。
    - auto-approve：无人值守全放行 —— 一切可由权限层决定的操作（含高危 / 不可逆写 /
      出站网络 / 无法归类）直接放行，不进入审批流、不因风险等级阻断。
    - high-risk-block：高危无条件阻断，不进入审批流。
    """

    def __init__(self, mode: PermissionMode = PermissionMode.INTERACTIVE) -> None:
        self.mode = mode
        self._engine = PolicyEngine()

    def classify(self, op: str, target: str, coeffect: list[str]) -> RiskLevel:
        return self._engine.classify(op, target, coeffect)

    def authorize(self, op: str, target: str, coeffect: list[str]) -> Decision:
        if self.mode is PermissionMode.AUTO_APPROVE:
            # 顶部短路：无人值守全放行，不调用 classify（模式不关心风险等级）。
            return Decision(True, f"auto-approve 模式全放行: {op}")
        risk = self.classify(op, target, coeffect)
        if self.mode is PermissionMode.READ_ONLY and risk in (
            RiskLevel.DATA_EDIT,
            RiskLevel.HIGH_RISK,
        ):
            raise AccessControlError(
                PermissionErrorCode.PERMISSION_DENIED,
                f"read-only 模式下拒绝 {risk.value} 操作: {op}",
            )
        if self.mode is PermissionMode.HIGH_RISK_BLOCK and risk is RiskLevel.HIGH_RISK:
            raise AccessControlError(
                PermissionErrorCode.PERMISSION_DENIED,
                f"high-risk-block 模式下一律阻断高危操作: {op}",
            )
        return self._engine.authorize(op, target, risk)
