"""权限（permission）：分级权限 + 人工审批 + 沙箱隔离。"""

from .approval import ApprovalChannel, ApprovalWorkflow, is_approved
from .errors import AccessControlError, PermissionErrorCode
from .guard import PermissionGuard
from .models import (
    ApprovalAction,
    ApprovalRequest,
    ApprovalResult,
    ApprovalTicket,
    Decision,
    PermissionMode,
    ResourceBudget,
    RiskLevel,
    SandboxDomain,
    SandboxHandle,
    SandboxResult,
)
from .policy import PermissionModeGate, PolicyEngine
from .sandbox import SandboxManager, SandboxPolicy

__all__ = [
    "AccessControlError",
    "ApprovalAction",
    "ApprovalChannel",
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalTicket",
    "ApprovalWorkflow",
    "Decision",
    "PermissionErrorCode",
    "PermissionGuard",
    "PermissionMode",
    "PermissionModeGate",
    "PolicyEngine",
    "ResourceBudget",
    "RiskLevel",
    "SandboxDomain",
    "SandboxHandle",
    "SandboxManager",
    "SandboxPolicy",
    "SandboxResult",
    "is_approved",
]
