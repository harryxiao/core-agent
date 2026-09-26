"""权限（permission）：分级权限 + 人工审批 + 沙箱隔离。"""

from .approval import ApprovalWorkflow
from .errors import AccessControlError, PermissionErrorCode
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
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalTicket",
    "ApprovalWorkflow",
    "Decision",
    "PermissionErrorCode",
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
]
