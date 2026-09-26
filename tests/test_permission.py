"""permission 单元测试（对齐规格场景 + §7 专属校验锚点）。

覆盖：风险分级、授权判定、审批放行/超时/过期/归档/改计划、
沙箱执行/不可用/幂等销毁/超配额、出站白名单 + 文件系统受控。
"""

from __future__ import annotations

import sys

import pytest

from core.permission import (
    AccessControlError,
    ApprovalAction,
    ApprovalRequest,
    ApprovalResult,
    ApprovalWorkflow,
    PermissionErrorCode,
    PermissionMode,
    PermissionModeGate,
    PolicyEngine,
    ResourceBudget,
    RiskLevel,
    SandboxManager,
    SandboxPolicy,
)


def _engine() -> PolicyEngine:
    return PolicyEngine()


def _request() -> ApprovalRequest:
    return ApprovalRequest(
        op="delete",
        target="/prod/db",
        impact_summary="删库",
        rollback_plan="备份恢复",
        trace_id="t1",
    )


# ---- 分级 ----


def test_classify_levels() -> None:
    engine = _engine()
    assert engine.classify("read_file", "/tmp/x", ["filesystem:read"]) == RiskLevel.READ
    assert engine.classify("write_file", "/tmp/x", ["filesystem:write"]) == RiskLevel.DATA_EDIT
    assert engine.classify("delete", "/prod", []) == RiskLevel.HIGH_RISK
    assert engine.classify("shell", "exec", []) == RiskLevel.HIGH_RISK
    assert engine.classify("call_api", "x", ["secret:key"]) == RiskLevel.HIGH_RISK
    assert engine.classify("call_api", "x", ["network:outbound"]) == RiskLevel.HIGH_RISK


def test_classify_unknown_deny_by_default() -> None:
    assert _engine().classify("xyzzy", "x", []) == RiskLevel.HIGH_RISK


# ---- 授权 ----


def test_authorize_high_risk_requires_approval() -> None:
    decision = _engine().authorize("delete", "/prod", RiskLevel.HIGH_RISK)
    assert decision.allowed is False
    assert decision.approval_required is True


def test_authorize_read_allowed() -> None:
    decision = _engine().authorize("read_file", "/tmp/x", RiskLevel.READ)
    assert decision.allowed is True
    assert decision.approval_required is False


# ---- 审批 ----


def test_approval_approved() -> None:
    workflow = ApprovalWorkflow()
    ticket = workflow.create(_request())
    result = workflow.ask(
        ticket, approver=lambda t: ApprovalResult(approved=True, approver="alice")
    )
    assert result.approved is True
    assert ticket.status == "approved"
    assert ticket in workflow.list_archived()


def test_approval_timeout_fail_closed() -> None:
    workflow = ApprovalWorkflow()
    ticket = workflow.create(_request())
    with pytest.raises(AccessControlError) as exc_info:
        workflow.ask(ticket)  # 无 approver → fail-closed
    assert exc_info.value.code is PermissionErrorCode.APPROVAL_TIMEOUT


def test_approval_expired() -> None:
    workflow = ApprovalWorkflow()
    request = ApprovalRequest(
        op="delete",
        target="/prod",
        impact_summary="x",
        rollback_plan="y",
        trace_id="t1",
        ttl_seconds=0.0,
    )
    ticket = workflow.create(request)
    with pytest.raises(AccessControlError) as exc_info:
        workflow.ask(ticket, approver=lambda t: ApprovalResult(approved=True))
    assert exc_info.value.code is PermissionErrorCode.APPROVAL_EXPIRED


def test_approval_edit_plan_supersedes() -> None:
    workflow = ApprovalWorkflow()
    ticket = workflow.create(_request())
    result = workflow.ask(
        ticket,
        approver=lambda t: ApprovalResult(
            approved=False, action=ApprovalAction.EDIT_PLAN, note="改计划"
        ),
    )
    assert result.approved is False
    assert ticket.status == "superseded"


def test_approval_archived() -> None:
    workflow = ApprovalWorkflow()
    ticket = workflow.create(_request())
    workflow.archive(ticket)  # 归档可回溯
    assert ticket in workflow.list_archived()


# ---- 沙箱 ----


def test_sandbox_run_executes() -> None:
    manager = SandboxManager()
    result = manager.run([sys.executable, "-c", "print('hi')"])
    assert result.exit_code == 0
    assert "hi" in result.stdout
    assert result.destroyed is True  # 执行完自动销毁


def test_sandbox_unavailable() -> None:
    def fail_backend(cmd, env, budget):
        raise RuntimeError("boom")

    manager = SandboxManager(backend=fail_backend)
    with pytest.raises(AccessControlError) as exc_info:
        manager.run(["echo", "hi"])
    assert exc_info.value.code is PermissionErrorCode.SANDBOX_UNAVAILABLE


def test_sandbox_destroy_idempotent() -> None:
    manager = SandboxManager()
    handle = manager.create()
    manager.destroy(handle)
    manager.destroy(handle)  # 幂等，不抛
    assert manager.active_handles() == []


def test_sandbox_quota_exceeded() -> None:
    manager = SandboxManager()
    budget = ResourceBudget(timeout_s=0.05)
    with pytest.raises(AccessControlError) as exc_info:
        manager.run([sys.executable, "-c", "import time; time.sleep(1)"], budget=budget)
    assert exc_info.value.code is PermissionErrorCode.QUOTA_EXCEEDED


# ---- 策略门 ----


def test_policy_outbound_deny() -> None:
    policy = SandboxPolicy(host_allowlist=["api.example.com"])
    with pytest.raises(AccessControlError) as exc_info:
        policy.check_outbound("evil.com")
    assert exc_info.value.code is PermissionErrorCode.PERMISSION_DENIED
    policy.check_outbound("api.example.com")  # 白名单放行


def test_policy_fs_controlled() -> None:
    policy = SandboxPolicy(fs_allowlist={"/data": "rw", "/readonly": "r"})
    with pytest.raises(AccessControlError):
        policy.check_fs("/etc/passwd")
    with pytest.raises(AccessControlError):
        policy.check_fs("/readonly", mode="w")
    policy.check_fs("/data", mode="w")  # 授权写


# ---- 权限模式（M6）----


def test_permission_mode_read_only_denies_write() -> None:
    gate = PermissionModeGate(PermissionMode.READ_ONLY)
    with pytest.raises(AccessControlError) as exc_info:
        gate.authorize("write_file", "/tmp/x", ["filesystem:write"])
    assert exc_info.value.code is PermissionErrorCode.PERMISSION_DENIED
    assert gate.authorize("read_file", "/tmp/x", ["filesystem:read"]).allowed is True


def test_permission_mode_interactive_high_risk_approval() -> None:
    gate = PermissionModeGate(PermissionMode.INTERACTIVE)
    decision = gate.authorize("delete", "/prod", [])
    assert decision.approval_required is True


def test_permission_mode_auto_approve_low_risk() -> None:
    gate = PermissionModeGate(PermissionMode.AUTO_APPROVE)
    assert gate.authorize("write_file", "/tmp/x", ["filesystem:write"]).allowed is True
    decision = gate.authorize("delete", "/prod", [])
    assert decision.approval_required is True  # 高危仍按高危策略走审批


def test_permission_mode_high_risk_block() -> None:
    gate = PermissionModeGate(PermissionMode.HIGH_RISK_BLOCK)
    with pytest.raises(AccessControlError) as exc_info:
        gate.authorize("delete", "/prod", [])
    assert exc_info.value.code is PermissionErrorCode.PERMISSION_DENIED
    assert gate.authorize("write_file", "/tmp/x", ["filesystem:write"]).allowed is True


def test_permission_mode_from_config() -> None:
    assert PermissionMode.from_config("read-only") is PermissionMode.READ_ONLY
    assert PermissionMode.from_config("unknown") is PermissionMode.INTERACTIVE
    assert PermissionMode.from_config(None) is PermissionMode.INTERACTIVE
