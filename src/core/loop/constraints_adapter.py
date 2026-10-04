"""constraints→loop 适配层：把熔断中间件接到 loop 的两个接缝（change 0052 / E1）。

- **before 接缝**（`middlewares`）：熔断打开 → 返回终止 Action（短路本轮，与 `decline` 同构）。
- **结果侧接缝**（`action_observers`）：执行结果回灌 `CircuitBreaker.record_result`。

熔断**按 `tool_id` 隔离**（`CircuitBreaker` 只有单计数器/单状态，直接接进 loop 会让一个坏工具
**全局开闸**）；**只计执行类失败**，策略性拒绝（输入校验 / coeffect 缺失 / 确认门拒绝）不计入
——否则模型可用坏参数把工具"锁死"。

适配层落 loop 侧：`constraints → loop` 是架构红线（`tests/test_architecture.py`），
而 `loop → constraints` 合法。对应规格：`doc/openspec/specs/constraints/spec.md`「容错中间件」；
ADR-0055。
"""

from __future__ import annotations

from collections.abc import Callable

from core.constraints import (
    CircuitBreaker,
    ConstraintError,
    ConstraintErrorCode,
    ExecContext,
    ExecRequest,
)
from core.loop.protocol import Action, ActionResult, LoopContext

# 策略性拒绝：不反映工具健康度，不计入熔断计数（也不影响其他工具）。
_POLICY_DENIALS = frozenset(
    {
        "INVALID_ARGS",
        "COEFFECT_MISSING",
        "GATE_DENIED",
        "IRREVERSIBLE_BLOCKED",
        "NO_TOOL_PROVIDER",
    }
)


class ConstraintsChain:
    """constraints 熔断链在 loop 接缝上的适配器（按 `tool_id` 隔离）。"""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        cooldown_s: float = 30.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self._clock = clock
        self.breakers: dict[str, CircuitBreaker] = {}

    def _breaker(self, tool_id: str) -> CircuitBreaker:
        breaker = self.breakers.get(tool_id)
        if breaker is None:
            breaker = CircuitBreaker(self.failure_threshold, self.cooldown_s, self._clock)
            self.breakers[tool_id] = breaker
        return breaker

    def middleware(self, ctx: LoopContext, action: Action) -> Action | None:
        """before 接缝：熔断打开则短路本轮（终止 Action），否则放行。"""
        if action.is_terminal:
            return action
        try:
            self._breaker(action.tool_id).before(
                ExecContext(trace_id=""), ExecRequest(action.tool_id, action.args, {}, "")
            )
        except ConstraintError as err:
            if err.code == ConstraintErrorCode.CIRCUIT_OPEN:
                return Action(
                    args={
                        "reply": f"已拒绝：工具 {action.tool_id} 熔断中（CIRCUIT_OPEN），本轮终止。"
                    }
                )
            raise
        return action

    def observe_result(self, ctx: LoopContext, action: Action, result: ActionResult) -> None:
        """结果接缝：执行类失败计入熔断；策略性拒绝不计入。"""
        if action.is_terminal:
            return
        if not result.failed:
            self._breaker(action.tool_id).record_result(success=True)
            return
        if result.error in _POLICY_DENIALS:
            return
        self._breaker(action.tool_id).record_result(success=False)


def build_constraints_chain(
    *,
    failure_threshold: int = 5,
    cooldown_s: float = 30.0,
    clock: Callable[[], float] | None = None,
) -> ConstraintsChain:
    """构造 constraints→loop 熔断链（阈值/冷却缺省取 `CircuitBreaker` 类默认）。"""
    return ConstraintsChain(failure_threshold=failure_threshold, cooldown_s=cooldown_s, clock=clock)
