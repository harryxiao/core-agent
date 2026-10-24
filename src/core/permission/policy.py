"""权限分级策略引擎（permission）。

按操作 / 目标 / coeffect **语义分词**分级：删杀 / 密钥 / 出站网络 → HIGH_RISK，
写 → DATA_EDIT，读 → READ，无法归类 → HIGH_RISK（deny-by-default）。

对应接口：doc/03-interfaces/permission-interface.md §2
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .errors import AccessControlError, PermissionErrorCode
from .models import Decision, PermissionMode, RiskLevel

_HIGH_RISK_TOKENS = frozenset(
    {
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
    }
)
_WRITE_TOKENS = frozenset(
    {
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
    }
)
_READ_TOKENS = frozenset(
    {
        "read",
        "get",
        "list",
        "search",
        "query",
        "cat",
        "view",
        "show",
        "stat",
        "process",  # 后台任务巡检（tools.process；kill 仍由高危词元优先判 HIGH_RISK）
    }
)
# 词元分隔符：命名空间（`.`）/ 路径（`/`）与 snake / kebab / coeffect 式（`_` `-` `:`）。
# 分级 SHALL 按**完整词元**命中，SHALL NOT 对标识串做任意子串匹配 ——
# 否则 `tools.target`（含子串 `get`）、`tools.category_sync`（含 `cat`）会被误判为只读，
# deny-by-default 兜底失效（规格「分级权限体系」/ change 0135）。
_TOKEN_SPLIT = re.compile(r"[._:\-/]+")
# 委托类 coeffect 的**字面量**只读豁免：SHALL NOT 放宽为 "agent:" 前缀，
# 否则将来任何 `agent:*` coeffect 会静默变只读（同 change 0095 的「按词元非子串」口径）。
_DELEGATE_COEFFECT = "agent:delegate"
# 后台任务清单工具的**字面量**只读豁免（change 0270 / ADR-0260）：`tools.tasks` 无只读词元；
# SHALL NOT 放宽为 `tasks` 词元/前缀 —— 否则未来含该词元的动作会静默变只读（deny-by-default 破口）。
_BACKGROUND_TASKS_TOOL = "tools.tasks"


def _tokens(op: str, target: str) -> set[str]:
    """把操作与目标切成**词元集合**（小写、按 `._:-/` 切分）。"""
    return {token for chunk in (op, target) for token in _TOKEN_SPLIT.split(chunk.lower()) if token}


class PolicyEngine:
    """风险分级与授权。"""

    def classify(  # noqa: PLR0911 — 分级规则按优先级逐条短路，分支清晰优于合并
        self, op: str, target: str, coeffect: list[str]
    ) -> RiskLevel:
        tokens = _tokens(op, target)
        if tokens & _HIGH_RISK_TOKENS:
            return RiskLevel.HIGH_RISK
        if any(
            c.startswith("secret:") or c.startswith("network:") or c == "external" for c in coeffect
        ):
            return RiskLevel.HIGH_RISK
        if _DELEGATE_COEFFECT in coeffect:  # list 元素等值匹配，非子串
            return RiskLevel.READ
        if op == _BACKGROUND_TASKS_TOOL:  # 字面量工具 id，非词元/前缀
            return RiskLevel.READ
        if tokens & _WRITE_TOKENS:
            return RiskLevel.DATA_EDIT
        if tokens & _READ_TOKENS:
            return RiskLevel.READ
        return RiskLevel.HIGH_RISK  # 无法归类 → deny-by-default

    def authorize(self, op: str, target: str, risk: RiskLevel) -> Decision:
        if risk == RiskLevel.HIGH_RISK:
            return Decision(
                False, f"高危操作 {op} 作用于 {target}，需人工审批", approval_required=True
            )
        return Decision(True, f"{risk.value} 操作放行")


# plan 模式只读工具面**显式排除**的委托工具（change 0313）：`tools.delegate` 的 coeffect
# 有字面量只读豁免（change 0095），不排除会让 plan 自动升级为多 Agent 派发。
_PLAN_EXCLUDED_TOOL = "tools.delegate"


def readonly_tool_ids(tools: Iterable[tuple[str, Sequence[str]]]) -> frozenset[str]:
    """只读工具面：``RiskLevel.READ`` 且显式排除委托工具（change 0313）。

    ``tools`` 为 ``(tool_id, coeffects)`` 序列（取自 ``ToolProvider.active_tools``）。
    分级口径委托 :meth:`PolicyEngine.classify`（单一真源），本函数不另立规则。
    """
    engine = PolicyEngine()
    return frozenset(
        tool_id
        for tool_id, coeffects in tools
        if tool_id != _PLAN_EXCLUDED_TOOL
        and engine.classify(tool_id, "", list(coeffects)) is RiskLevel.READ
    )


class PermissionModeGate:
    """权限模式门：四档启动开关，覆盖 :class:`PolicyEngine` 的默认授权。

    - read-only：拒绝写 / 编辑 / 删除类操作（``PERMISSION_DENIED``）。
    - interactive：高危走人工审批（默认行为）。
    - auto-approve：无人值守全放行 —— 一切可由权限层决定的操作（含高危 / 不可逆写 /
      出站网络 / 无法归类）直接放行，不进入审批流、不因风险等级阻断。
      可选 ``allowed_coeffects`` 收窄放行面（change 0280）：动作声明的任一 coeffect
      不在集合内 ⇒ `PERMISSION_DENIED`；空集合 = 不限制（既有全放行语义）。
    - high-risk-block：高危无条件阻断，不进入审批流。
    """

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.INTERACTIVE,
        *,
        allowed_coeffects: frozenset[str] | None = None,
    ) -> None:
        self.mode = mode
        self._engine = PolicyEngine()
        # 空集合与 None 等价（不限制），避免「配置了空值 ⇒ 全部拒绝」的意外锁死。
        self._allowed_coeffects = frozenset(allowed_coeffects) if allowed_coeffects else None

    def classify(self, op: str, target: str, coeffect: list[str]) -> RiskLevel:
        return self._engine.classify(op, target, coeffect)

    def authorize(self, op: str, target: str, coeffect: list[str]) -> Decision:
        if self.mode is PermissionMode.AUTO_APPROVE:
            # 顶部短路：无人值守全放行，不调用 classify（模式不关心风险等级）。
            # 允许面（change 0280）在放行前检查：声明的**任一** coeffect 越界即拒绝。
            denied = self._denied_coeffects(coeffect)
            if denied:
                raise AccessControlError(
                    PermissionErrorCode.PERMISSION_DENIED,
                    f"auto-approve 允许面拒绝 {op}（未授权 coeffect: {', '.join(denied)}）",
                )
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

    def _denied_coeffects(self, coeffect: list[str]) -> list[str]:
        """允许面检查：返回不在白名单内的 coeffect（空列表 = 通过 / 未配置）。"""
        if self._allowed_coeffects is None:
            return []
        return [name for name in coeffect if name not in self._allowed_coeffects]
