"""人工审批工作流（permission）。

create → ask → archive：TTL 过期抛 APPROVAL_EXPIRED，无 approver 抛
APPROVAL_TIMEOUT（fail-closed），approver 回调返回 approve/reject/edit-plan。

对应接口：doc/03-interfaces/permission-interface.md §4
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from .errors import AccessControlError, PermissionErrorCode
from .models import ApprovalAction, ApprovalRequest, ApprovalResult, ApprovalTicket

_STATUS_PENDING = "pending"
_STATUS_APPROVED = "approved"
_STATUS_REJECTED = "rejected"
_STATUS_EXPIRED = "expired"
_STATUS_TIMEOUT = "timeout"
_STATUS_SUPERSEDED = "superseded"


class ApprovalWorkflow:
    """审批单生命周期与归档。"""

    def __init__(self) -> None:
        self._archive: list[ApprovalTicket] = []

    def create(self, request: ApprovalRequest) -> ApprovalTicket:
        return ApprovalTicket(
            ticket_id=uuid.uuid4().hex,
            request=request,
            status=_STATUS_PENDING,
            created_at=time.time(),
        )

    def ask(
        self,
        ticket: ApprovalTicket,
        approver: Callable[[ApprovalTicket], ApprovalResult] | None = None,
    ) -> ApprovalResult:
        if time.time() > ticket.created_at + ticket.request.ttl_seconds:
            ticket.status = _STATUS_EXPIRED
            raise AccessControlError(
                PermissionErrorCode.APPROVAL_EXPIRED, f"审批单 {ticket.ticket_id} 已过期"
            )
        if approver is None:
            ticket.status = _STATUS_TIMEOUT
            raise AccessControlError(PermissionErrorCode.APPROVAL_TIMEOUT, "审批超时，fail-closed")
        return self._resolve(ticket, approver(ticket))

    def approve(
        self, ticket: ApprovalTicket, approver: str = "human", note: str | None = None
    ) -> ApprovalResult:
        """人工批准：放行并归档，可回溯。"""
        return self._resolve(
            ticket,
            ApprovalResult(
                approved=True, approver=approver, note=note, action=ApprovalAction.APPROVE
            ),
        )

    def reject(
        self, ticket: ApprovalTicket, approver: str = "human", note: str | None = None
    ) -> ApprovalResult:
        """人工拒绝：阻断并附拒绝理由，供后续提案改进。"""
        return self._resolve(
            ticket,
            ApprovalResult(
                approved=False, approver=approver, note=note, action=ApprovalAction.REJECT
            ),
        )

    def edit_plan(
        self,
        ticket: ApprovalTicket,
        request: ApprovalRequest,
        approver: str = "human",
        note: str | None = None,
    ) -> ApprovalTicket:
        """编辑计划后重提：原单标 superseded，修订计划形成新审批单（pending）。"""
        self._resolve(
            ticket,
            ApprovalResult(
                approved=False, approver=approver, note=note, action=ApprovalAction.EDIT_PLAN
            ),
        )
        return self.create(request)

    def _resolve(self, ticket: ApprovalTicket, result: ApprovalResult) -> ApprovalResult:
        """按审批动作分级路由：approve→approved / reject→rejected / edit-plan→superseded。"""
        if result.action == ApprovalAction.EDIT_PLAN:
            ticket.status = _STATUS_SUPERSEDED
        elif result.approved:
            ticket.status = _STATUS_APPROVED
        else:
            ticket.status = _STATUS_REJECTED
        ticket.resolved_at = time.time()
        ticket.result = result
        self._archive.append(ticket)
        return result

    def archive(self, ticket: ApprovalTicket) -> None:
        if ticket not in self._archive:
            self._archive.append(ticket)

    def list_archived(self) -> list[ApprovalTicket]:
        return list(self._archive)
