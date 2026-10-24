"""会话级执行模式与计划草案（ui）。

`agent_mode ∈ {quick, plan}` 与 `PlanDraft` 均为**会话作用域的进程内临时状态**
（change 0313 / ADR-0303）：不落盘、不写会话注册表、不跨进程。同一会话至多一份
草案，新草案覆盖旧草案；草案被批准 / 放弃后一次性消费。

对应接口：doc/03-interfaces/ui-interface.md §1.1
"""

from __future__ import annotations

from dataclasses import dataclass

from core.orchestration import Plan

from .errors import UiError, UiErrorCode

# 执行模式取值（词表单一真源；非法值拒绝而非静默归一）
AGENT_MODES: frozenset[str] = frozenset({"quick", "plan"})
DEFAULT_AGENT_MODE = "quick"


@dataclass
class PlanDraft:
    """待审批的计划草案：目标 / 子任务 DAG / 波次 / 成功标准 / 勘察结论（仅内存）。"""

    draft_id: str
    session_id: str
    goal: str
    plan: Plan
    exploration: str = ""
    created_at: float = 0.0


class PlanSessions:
    """会话级模式与草案登记：进程内 dict，按 ``session_id`` 分桶。"""

    def __init__(self) -> None:
        self._modes: dict[str, str] = {}
        self._drafts: dict[str, PlanDraft] = {}

    def mode(self, session_id: str) -> str:
        """读执行模式（缺省 ``quick``）。"""
        return self._modes.get(session_id, DEFAULT_AGENT_MODE)

    def set_mode(self, session_id: str, mode: str) -> None:
        """置执行模式；非法值拒绝且不改原值。"""
        if mode not in AGENT_MODES:
            raise UiError(
                UiErrorCode.UI_PLAN_MODE_INVALID,
                f"非法执行模式：{mode}（可选：quick/plan）",
            )
        self._modes[session_id] = mode

    def put(self, draft: PlanDraft) -> None:
        """登记草案：同会话覆盖旧草案（至多一份）。"""
        self._drafts[draft.session_id] = draft

    def get(self, session_id: str, draft_id: str) -> PlanDraft | None:
        """取草案（会话隔离 + 标识匹配）；不存在 / 非本会话 ⇒ None。"""
        draft = self._drafts.get(session_id)
        if draft is None or draft.draft_id != draft_id:
            return None
        return draft

    def take(self, session_id: str, draft_id: str) -> PlanDraft | None:
        """一次性消费草案；返回草案并清空该会话槽位。"""
        draft = self.get(session_id, draft_id)
        if draft is not None:
            self._drafts.pop(session_id, None)
        return draft

    def discard(self, session_id: str, draft_id: str) -> bool:
        """丢弃草案；返回是否确有草案被丢弃。"""
        return self.take(session_id, draft_id) is not None
