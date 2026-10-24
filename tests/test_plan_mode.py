"""plan 模式（change 0313）：会话级模式、只读计划轮、临时草案与 y/n 审批。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from core.configuration.models import LLMConfig
from core.loop import LoopEvent, LoopResult
from core.orchestration import OrchestrationError, OrchestrationErrorCode, Plan, Subtask
from core.permission.policy import readonly_tool_ids
from core.tools import Tool, ToolDef, ToolProvider
from core.ui import Event, UIAPILayer, UiError, UiErrorCode
from core.ui.plan import PlanDraft, PlanSessions
from core.ui.sessions import SessionRegistry


def _llm(key: str = "${OPENAI_API_KEY}") -> LLMConfig:
    return LLMConfig(provider="openai", model="gpt-4o", endpoint="https://x", api_key_ref=key)


class _PlanLoop:
    """只读计划循环替身：记录输入/会话，回放一段勘察结论。"""

    def __init__(self, reply: str = "勘察结论：仓库是 Python 项目") -> None:
        self.reply = reply
        self.inputs: list[str] = []
        self.sessions: list[str] = []

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        self.inputs.append(user_input)
        self.sessions.append(session_id)
        yield LoopEvent("reply_delta", {"text": self.reply})
        yield LoopEvent("loop_finished", LoopResult(reply=self.reply, trace_id="t-plan"))


class _Orchestrator:
    """编排器替身：记录草案请求与执行请求。"""

    def __init__(self) -> None:
        self.drafts: list[dict[str, Any]] = []
        self.runs: list[dict[str, Any]] = []
        self.fail_draft = False

    async def draft_plan(
        self, goal: str, success_criteria: list[str] | None = None, *, context: str = ""
    ) -> Plan:
        self.drafts.append({"goal": goal, "criteria": success_criteria, "context": context})
        if self.fail_draft:
            raise OrchestrationError(OrchestrationErrorCode.SUBTASK_EXECUTION_FAILED, "拆解失败")
        return Plan(
            subtasks=[Subtask(id="1", goal=goal, acceptance="完成")],
            goal=goal,
            order=["1"],
            success_criteria=list(success_criteria or []),
            waves=[["1"]],
        )

    async def astream(self, task_id: str, goal: str, **kwargs: Any) -> AsyncIterator[LoopEvent]:
        self.runs.append({"task_id": task_id, "goal": goal, **kwargs})
        yield LoopEvent("task_started", {"task_id": task_id, "goal": goal})
        yield LoopEvent("task_finished", {"task_id": task_id, "ok": True})


def _api(
    *, plan_loop: Any = None, orchestrator: Any = None, registry: SessionRegistry | None = None
) -> tuple[UIAPILayer, str]:
    kwargs: dict[str, Any] = {}
    if plan_loop is not None:
        kwargs["plan_loop"] = plan_loop
    if orchestrator is not None:
        kwargs["orchestrator"] = orchestrator
    if registry is not None:
        kwargs["registry"] = registry
    api = UIAPILayer(**kwargs)
    api.set_llm_config(_llm())
    session_id = api.create_session("tui")
    return api, session_id


async def _collect(stream: AsyncIterator[Event]) -> list[Event]:
    return [event async for event in stream]


def _draft(session_id: str = "s", draft_id: str = "draft-1") -> PlanDraft:
    plan = Plan(
        subtasks=[Subtask(id="1", goal="g", acceptance="")],
        goal="goal",
        order=["1"],
        waves=[["1"]],
    )
    return PlanDraft(
        draft_id=draft_id,
        session_id=session_id,
        goal="goal",
        plan=plan,
        exploration="internal",
        created_at=0.0,
    )


# ---- PlanSessions ----


def test_plan_sessions_default_quick_and_invalid_mode() -> None:
    sessions = PlanSessions()
    assert sessions.mode("s") == "quick"
    sessions.set_mode("s", "plan")
    assert sessions.mode("s") == "plan"
    with pytest.raises(UiError) as exc:
        sessions.set_mode("s", "planx")
    assert exc.value.code == UiErrorCode.UI_PLAN_MODE_INVALID
    assert sessions.mode("s") == "plan"  # 非法值不归一、不改原值


def test_plan_sessions_draft_is_single_and_one_shot() -> None:
    sessions = PlanSessions()
    first = _draft(draft_id="d1")
    second = _draft(draft_id="d2")
    sessions.put(first)
    sessions.put(second)  # 同会话覆盖旧草案
    assert sessions.get("s", "d1") is None
    assert sessions.get("s", "d2") is second
    assert sessions.get("other", "d2") is None  # 会话隔离
    assert sessions.take("s", "d2") is second
    assert sessions.take("s", "d2") is None  # 一次性消费


# ---- 计划轮 ----


def test_run_plan_turn_emits_draft_without_exploration() -> None:
    loop = _PlanLoop()
    orch = _Orchestrator()
    api, sid = _api(plan_loop=loop, orchestrator=orch)
    api.set_agent_mode(sid, "plan")

    events = asyncio.run(_collect(api.run_plan_turn(sid, "实现登录")))

    assert [event.type for event in events] == ["loop.delta", "loop.result", "plan.draft_ready"]
    assert loop.inputs == ["实现登录"]
    assert loop.sessions == [sid]
    assert orch.drafts[0]["goal"] == "实现登录"
    assert "仓库是 Python 项目" in orch.drafts[0]["context"]  # 勘察结论喂给拆解
    payload = events[-1].payload
    assert isinstance(payload, dict)
    assert payload["goal"] == "实现登录"
    assert payload["subtasks"][0]["id"] == "1"
    assert "exploration" not in payload
    assert "仓库是 Python 项目" not in json.dumps(payload, ensure_ascii=False)
    assert api.agent_mode(sid) == "plan"  # 批准前仍在 plan


def test_run_plan_turn_requires_plan_mode() -> None:
    orch = _Orchestrator()
    api, sid = _api(plan_loop=_PlanLoop(), orchestrator=orch)
    with pytest.raises(UiError) as exc:
        asyncio.run(_collect(api.run_plan_turn(sid, "做点事")))
    assert exc.value.code == UiErrorCode.UI_PLAN_MODE_INVALID
    assert orch.drafts == []


def test_run_plan_turn_unavailable_without_dependencies() -> None:
    api_no_loop, sid_no_loop = _api(orchestrator=_Orchestrator())
    api_no_loop.set_agent_mode(sid_no_loop, "plan")
    with pytest.raises(UiError) as exc:
        asyncio.run(_collect(api_no_loop.run_plan_turn(sid_no_loop, "做点事")))
    assert exc.value.code == UiErrorCode.UI_PLAN_UNAVAILABLE

    api_no_orch, sid_no_orch = _api(plan_loop=_PlanLoop())
    api_no_orch.set_agent_mode(sid_no_orch, "plan")
    with pytest.raises(UiError) as exc2:
        asyncio.run(_collect(api_no_orch.run_plan_turn(sid_no_orch, "做点事")))
    assert exc2.value.code == UiErrorCode.UI_PLAN_UNAVAILABLE


def test_run_plan_turn_draft_failure_is_structured() -> None:
    orch = _Orchestrator()
    orch.fail_draft = True
    api, sid = _api(plan_loop=_PlanLoop(), orchestrator=orch)
    api.set_agent_mode(sid, "plan")
    with pytest.raises(UiError) as exc:
        asyncio.run(_collect(api.run_plan_turn(sid, "做点事")))
    assert exc.value.code == UiErrorCode.UI_PLAN_DRAFT_FAILED
    assert api.agent_mode(sid) == "plan"  # 失败不偷偷退回 quick


# ---- 审批 ----


def test_approve_plan_executes_approved_plan_and_returns_quick() -> None:
    orch = _Orchestrator()
    api, sid = _api(plan_loop=_PlanLoop(), orchestrator=orch)
    api.set_agent_mode(sid, "plan")
    events = asyncio.run(_collect(api.run_plan_turn(sid, "实现登录")))
    draft_id = events[-1].payload["draft_id"]

    task_events = asyncio.run(_collect(api.approve_plan(sid, draft_id)))

    assert [event.type for event in task_events] == ["task.task_started", "task.task_finished"]
    run = orch.runs[0]
    assert run["goal"] == "实现登录"
    assert run["session_id"] == sid
    assert run["self_run"] is True
    assert run["plan"].goal == "实现登录"
    assert api.agent_mode(sid) == "quick"
    # 一次性消费：同一草案不可重放
    with pytest.raises(UiError) as exc:
        asyncio.run(_collect(api.approve_plan(sid, draft_id)))
    assert exc.value.code == UiErrorCode.UI_PLAN_DRAFT_NOT_FOUND


def test_discard_plan_drops_draft_and_returns_quick() -> None:
    orch = _Orchestrator()
    api, sid = _api(plan_loop=_PlanLoop(), orchestrator=orch)
    api.set_agent_mode(sid, "plan")
    events = asyncio.run(_collect(api.run_plan_turn(sid, "实现登录")))
    draft_id = events[-1].payload["draft_id"]

    assert api.discard_plan(sid, draft_id) is True
    assert api.agent_mode(sid) == "quick"
    assert api.discard_plan(sid, draft_id) is False
    with pytest.raises(UiError) as exc:
        asyncio.run(_collect(api.approve_plan(sid, draft_id)))
    assert exc.value.code == UiErrorCode.UI_PLAN_DRAFT_NOT_FOUND
    assert orch.runs == []


def test_plan_mode_does_not_touch_registry(tmp_path: Path) -> None:
    registry = SessionRegistry(path=tmp_path / "conversations.json")
    api, sid = _api(registry=registry)
    before = (tmp_path / "conversations.json").read_text(encoding="utf-8")

    api.set_agent_mode(sid, "plan")
    api.set_agent_mode(sid, "quick")

    assert (tmp_path / "conversations.json").read_text(encoding="utf-8") == before


# ---- 只读工具面 ----


def test_readonly_tool_ids_are_read_level_and_exclude_delegate() -> None:
    ids = readonly_tool_ids(
        [
            ("tools.file_read", ["filesystem:read"]),
            ("tools.delegate", ["agent:delegate"]),
            ("tools.file_write", ["filesystem:write"]),
            ("tools.code_run", ["process:spawn", "filesystem:write"]),
            ("tools.web_fetch", ["network:outbound"]),
            ("tools.tasks", ["task:read"]),
        ]
    )
    assert "tools.file_read" in ids
    assert "tools.tasks" in ids
    assert "tools.delegate" not in ids
    assert "tools.file_write" not in ids
    assert "tools.code_run" not in ids
    assert "tools.web_fetch" not in ids


def _tool(tool_id: str, coeffects: list[str]) -> Tool:
    return Tool(
        definition=ToolDef(
            tool_id=tool_id,
            description=tool_id,
            schema={"type": "object", "properties": {}},
            coeffects=coeffects,
            reversible=False,
        ),
        handler=lambda **_: "ok",
    )


def test_tool_subset_view_hides_and_blocks_excluded_tools() -> None:
    provider = ToolProvider()
    provider.register(_tool("tools.file_read", ["filesystem:read"]))
    provider.register(_tool("tools.file_write", ["filesystem:write"]))

    view = provider.subset({"tools.file_read"})

    assert [tool.tool_id for tool in view.active_tools()] == ["tools.file_read"]
    result = asyncio.run(view.ainvoke("tools.file_write", {}, trace_id="t"))
    assert result.ok is False
    assert result.error is not None
    assert "未知工具" in result.error.message
    # 底层注册表不受影响
    assert {tool.tool_id for tool in provider.active_tools()} == {
        "tools.file_read",
        "tools.file_write",
    }
