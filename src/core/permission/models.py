"""权限数据模型（permission）。

风险等级 / 审批单据 / 沙箱预算与结果 / 沙箱域 等数据结构。

对应接口：doc/03-interfaces/permission-interface.md §1
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RiskLevel(StrEnum):
    """操作风险分级。"""

    READ = "read"
    DATA_EDIT = "data-edit"
    HIGH_RISK = "high-risk"


class SandboxDomain(StrEnum):
    """沙箱隔离域：终端实跑，浏览器 / 文件系统为策略门。"""

    TERMINAL = "terminal"
    BROWSER = "browser"
    FILESYSTEM = "filesystem"


class ApprovalAction(StrEnum):
    """审批动作分级协议。"""

    APPROVE = "approve"
    REJECT = "reject"
    EDIT_PLAN = "edit-plan"


@dataclass
class Decision:
    """授权决策。"""

    allowed: bool
    reason: str
    approval_required: bool = False


@dataclass
class ApprovalRequest:
    """人工审批请求：操作 / 目标 / 影响 / 回滚计划 / 追溯 / TTL。"""

    op: str
    target: str
    impact_summary: str
    rollback_plan: str
    trace_id: str
    ttl_seconds: float = 300.0


@dataclass
class ApprovalResult:
    """审批结果。"""

    approved: bool
    approver: str | None = None
    note: str | None = None
    action: ApprovalAction = ApprovalAction.APPROVE


@dataclass
class ApprovalTicket:
    """审批单：承载请求、状态与最终结果，归档可追溯。"""

    ticket_id: str
    request: ApprovalRequest
    status: str
    created_at: float
    resolved_at: float | None = None
    result: ApprovalResult | None = None


@dataclass
class ResourceBudget:
    """沙箱资源配额。"""

    timeout_s: float = 30.0
    max_memory_bytes: int | None = None
    max_cpu_seconds: float | None = None


@dataclass
class SandboxHandle:
    """沙箱句柄：注册表回收的最小标识。"""

    handle_id: str
    kind: str


@dataclass
class SandboxResult:
    """沙箱执行结果。"""

    exit_code: int
    stdout: str
    stderr: str
    destroyed: bool
