"""auto-approve 全放行端到端回归（change 0095）。

确认门有两条独立来源，本文件分别验证 auto-approve 档下的净效果：
- `PermissionModeGate.authorize` 顶部短路（出站网络 / 不可归类动作）；
- `PermissionGuard.confirm` 不可逆写分支感知权限档（`code_run` 类不可逆工具）。

并回归：read-only / high-risk-block 两拒绝档语义未松动、guardrail 红线仍拦、
无 approver 的 `DefaultLoop` 在 auto-approve 下正向执行不可逆动作。
"""

from __future__ import annotations

from typing import Any

from core.judgment import DecisionPrimitive, DecisionResult
from core.loop import Action, DefaultLoop
from core.permission import PermissionGuard
from core.plugin_registry import CoeffectResolver
from core.tools import Tool, ToolDef, ToolProvider


class _FakeGuardrail:
    """duck-typed judgment 守卫：check() 返回给定 noul 结论。"""

    def __init__(self, noul: bool) -> None:
        self._noul = noul
        self.calls = 0

    def check(self, state: dict[str, Any], action: dict[str, Any], threshold: float | None = None):
        self.calls += 1
        return DecisionResult(
            primitive=DecisionPrimitive.NOUL,
            answers={"noul": {"noul": self._noul}},
            fallback=False,
        )


# ---- 来源 ①：PermissionModeGate 顶部短路 ----


def test_auto_approve_releases_irreversible_write() -> None:
    """不可逆写（走 guard 的不可逆分支）在 auto-approve 下放行。"""
    guard = PermissionGuard(mode="auto-approve")
    decision = guard.confirm(
        "tools.code_run", {"cmd": "rm -rf /tmp/x"}, ["filesystem:write"], reversible=False
    )
    assert decision.action == "auto"


def test_auto_approve_releases_outbound_network() -> None:
    """出站网络动作：interactive 走审批，auto-approve 直接放行（可见差异）。"""
    coeffects = ["network:outbound"]
    interactive = PermissionGuard(mode="interactive")
    assert (
        interactive.confirm("tools.web_fetch", {"url": "https://x"}, coeffects, True).action
        == "confirm"
    )
    auto = PermissionGuard(mode="auto-approve")
    assert auto.confirm("tools.web_fetch", {"url": "https://x"}, coeffects, True).action == "auto"


def test_auto_approve_releases_unclassifiable() -> None:
    """无法归类的动作（deny-by-default 高危兜底）在 auto-approve 下放行。"""
    auto = PermissionGuard(mode="auto-approve")
    assert auto.confirm("tools.whatever", {"path": "x"}, [], True).action == "auto"


# ---- 正交红线：guardrail 仍拦 ----


def test_auto_approve_honours_guardrail_deny() -> None:
    """auto-approve 全放行不越过正交 guardrail 红线。"""
    guardrail = _FakeGuardrail(noul=False)
    guard = PermissionGuard(mode="auto-approve", guardrail=guardrail)
    decision = guard.confirm("tools.code_run", {"cmd": "x"}, ["filesystem:write"], False)
    assert decision.action == "deny"
    assert guardrail.calls == 1


def test_auto_approve_honours_guardrail_allow() -> None:
    """guardrail 放行时 auto-approve 仍全放行（不因红线机制过度收窄）。"""
    guardrail = _FakeGuardrail(noul=True)
    guard = PermissionGuard(mode="auto-approve", guardrail=guardrail)
    decision = guard.confirm("tools.code_run", {"cmd": "x"}, ["filesystem:write"], False)
    assert decision.action == "auto"
    assert guardrail.calls == 1


# ---- 两拒绝档语义未松动 ----


def test_read_only_still_denies() -> None:
    guard = PermissionGuard(mode="read-only")
    assert guard.confirm("tools.file_write", {"path": "x"}, ["filesystem:write"], False).action == (
        "deny"
    )
    assert guard.confirm("tools.file_read", {"path": "x"}, ["filesystem:read"], True).action == (
        "auto"
    )


def test_high_risk_block_still_denies() -> None:
    guard = PermissionGuard(mode="high-risk-block")
    assert guard.confirm("tools.code_run", {"cmd": "x"}, [], True).action == "deny"


# ---- 端到端：DefaultLoop 无 approver ----


def _write_tool(seen: list[str]) -> Tool:
    return Tool(
        definition=ToolDef(
            tool_id="tools.echo",
            description="echo",
            schema={"type": "object", "properties": {"text": {"type": "string"}}},
            coeffects=["filesystem:write"],
            reversible=False,
        ),
        handler=lambda text: seen.append(text) or f"echo:{text}",
    )


def _irreversible_planner(ctx) -> Action:
    if ctx.rounds == 0:
        return Action(tool_id="tools.echo", args={"text": "hi"}, is_irreversible=True)
    return Action(args={"reply": "done"})


def _provider(seen: list[str]) -> ToolProvider:
    resolver = CoeffectResolver()
    resolver.register("filesystem:write", True)
    provider = ToolProvider(coeffect_resolver=resolver)
    provider.register(_write_tool(seen))
    return provider


def test_loop_auto_approve_executes_without_approver() -> None:
    """无 approver 的 DefaultLoop 在 auto-approve 下真实执行不可逆动作。"""
    seen: list[str] = []
    loop = DefaultLoop(
        planner=_irreversible_planner,
        tools=_provider(seen),
        gate=PermissionGuard(mode="auto-approve"),
    )
    result = loop.run("hi")
    assert seen == ["hi"]  # 工具确已执行（非被拒短路）
    assert result.reply == "done"


def test_loop_interactive_without_approver_denies() -> None:
    """对照：interactive + 无 approver 仍 fail-closed 拒绝（auto-approve 的差异来源）。"""
    seen: list[str] = []
    loop = DefaultLoop(
        planner=_irreversible_planner,
        tools=_provider(seen),
        gate=PermissionGuard(mode="interactive"),
    )
    result = loop.run("hi")
    assert seen == []
    assert result.reply.startswith("已拒绝")
