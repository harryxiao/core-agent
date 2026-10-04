"""constraints→loop 适配层测试（change 0052 / 账本 E1）。

证明熔断在生产接线下真正开合：按 tool_id 隔离、策略性拒绝不计入、冷却后半开闭合、
熔断打开转终止 Action 且不逃逸异常。适配层单测不依赖 build_runtime，更精确。
"""

from __future__ import annotations

from core.loop import Action, ActionResult, DefaultLoop, LoopContext
from core.loop.constraints_adapter import ConstraintsChain, build_constraints_chain
from core.tools import Tool, ToolDef, ToolProvider


def _fail(error: str) -> ActionResult:
    return ActionResult(failed=True, error=error)


def _ok() -> ActionResult:
    return ActionResult(failed=False, data="done")


def test_exec_failures_open_breaker_and_short_circuit() -> None:
    """连续执行失败达阈值 → 该工具的 middleware 返回终止 Action（CIRCUIT_OPEN）。"""
    chain = build_constraints_chain(failure_threshold=2, cooldown_s=30.0)
    ctx = LoopContext()
    action = Action(tool_id="tools.a", args={})
    # 阈值内放行
    decided = chain.middleware(ctx, action)
    assert decided is not None and not decided.is_terminal
    chain.observe_result(ctx, action, _fail("EXECUTION_FAILED"))
    chain.observe_result(ctx, action, _fail("TIMEOUT"))
    # 达阈值后快速失败（终止 Action，非异常逃逸）
    opened = chain.middleware(ctx, action)
    assert opened is not None and opened.is_terminal
    assert "CIRCUIT_OPEN" in str(opened.args.get("reply", ""))


def test_breaker_isolated_per_tool() -> None:
    """工具 A 熔断不影响工具 B。"""
    chain = build_constraints_chain(failure_threshold=2, cooldown_s=30.0)
    ctx = LoopContext()
    a, b = Action(tool_id="tools.a", args={}), Action(tool_id="tools.b", args={})
    for _ in range(2):
        chain.observe_result(ctx, a, _fail("EXECUTION_FAILED"))
    assert chain.middleware(ctx, a).is_terminal  # A 打开
    assert not chain.middleware(ctx, b).is_terminal  # B 健康，放行


def test_policy_denials_do_not_count() -> None:
    """策略性拒绝（校验/coeffect/确认门）远超阈值仍不熔断。"""
    chain = build_constraints_chain(failure_threshold=2, cooldown_s=30.0)
    ctx = LoopContext()
    action = Action(tool_id="tools.a", args={})
    for code in ("INVALID_ARGS", "COEFFECT_MISSING", "GATE_DENIED", "IRREVERSIBLE_BLOCKED"):
        for _ in range(5):
            chain.observe_result(ctx, action, _fail(code))
    # 仍闭合：放行
    assert not chain.middleware(ctx, action).is_terminal


def test_half_open_recovery_closes_breaker() -> None:
    """冷却后半开试探成功 → 闭合，后续失败计数重置。"""
    now = [0.0]
    chain = build_constraints_chain(failure_threshold=2, cooldown_s=10.0, clock=lambda: now[0])
    ctx = LoopContext()
    action = Action(tool_id="tools.a", args={})
    for _ in range(2):
        chain.observe_result(ctx, action, _fail("EXECUTION_FAILED"))
    assert chain.middleware(ctx, action).is_terminal  # OPEN
    now[0] = 20.0  # 过冷却 → HALF_OPEN
    assert not chain.middleware(ctx, action).is_terminal  # 试探放行
    chain.observe_result(ctx, action, _ok())  # 试探成功 → CLOSED
    # 计数已重置：单次失败不再开闸（阈值 2）
    chain.observe_result(ctx, action, _fail("EXECUTION_FAILED"))
    assert not chain.middleware(ctx, action).is_terminal


def test_terminal_action_passthrough_and_no_breaker() -> None:
    """终止动作（本轮回复）直通，不建熔断、不计数。"""
    chain = build_constraints_chain(failure_threshold=1, cooldown_s=30.0)
    ctx = LoopContext()
    terminal = Action(args={"reply": "done"})
    assert chain.middleware(ctx, terminal) is terminal
    chain.observe_result(ctx, terminal, _ok())  # 无副作用、无异常
    assert chain.breakers == {}  # 未为终止动作建熔断


def test_default_thresholds_are_class_defaults() -> None:
    """未传阈值时用 CircuitBreaker 类默认（5 / 30s）。"""
    chain = ConstraintsChain()
    assert chain.failure_threshold == 5  # noqa: PLR2004 — 类默认
    assert chain.cooldown_s == 30.0  # noqa: PLR2004 — 类默认


def test_e2e_breaker_opens_through_loop() -> None:
    """经 loop 驱动：连续执行失败达阈值后，工具 handler 不再被调用（快速失败）。"""
    threshold = 3
    chain = build_constraints_chain(failure_threshold=threshold, cooldown_s=30.0)
    calls: list[dict] = []

    def boom(**kw):
        calls.append(kw)
        raise RuntimeError("boom")

    provider = ToolProvider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.boom",
                description="",
                schema={"type": "object"},
                coeffects=[],
                reversible=True,
            ),
            handler=boom,
        )
    )
    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.boom", args={}),
        tools=provider,
        middlewares=[chain.middleware],
        action_observers=[chain.observe_result],
        max_rounds=10,
    )
    result = loop.run("hi")
    assert len(calls) == threshold  # 达阈值后不再真正执行
    assert "CIRCUIT_OPEN" in result.reply
