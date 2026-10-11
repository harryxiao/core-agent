"""constraints→loop 容错适配层：把重试中间件接到 loop 的执行接缝（change 0209 / ADR-0199）。

`FaultChain.wrap(act)` 包裹 `DefaultLoop.act`：工具调用**执行类失败**（超时 / 执行异常）且该工具
**可逆**时，按 `RetryPolicy` 退避重试；重试**耗尽原样返回最后一次失败结果**（不降级、不改码）
—— 保住 loop 的失败态语义（失败致本轮 trace 回滚、工具失败不判轮失败）。

- **显式白名单** `_RETRIABLE`：只有 `TIMEOUT` / `EXECUTION_FAILED` 重试，未来错误码 fail-closed。
- **仅可逆工具**：`tool_id` 惰性查 `provider.active_tools()` 得可逆集合（只在失败路径算一次并
  缓存）；不可逆工具不重试（避免部分外写被重试放大）。
- **不重跑中间件**：包裹的是 `act`，`middlewares` / `action_observers` 在 loop 侧逐次生效，
  语义不变。

适配层落 loop 侧：`constraints → loop` 是架构红线（`tests/test_architecture.py`），而
`loop → constraints` 合法。对应规格：`doc/openspec/specs/constraints/spec.md`「容错中间件」。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from core.constraints import RetryPolicy
from core.loop.protocol import ActFn, Action, ActionResult
from core.tools import ToolProvider

# 可重试的**执行类**失败码（显式白名单；策略性拒绝 / 未来新增码一律 fail-closed 不重试）。
_RETRIABLE = frozenset({"TIMEOUT", "EXECUTION_FAILED"})


class RetriableToolFailureError(Exception):
    """承载可重试失败码的轻量异常（供 `RetryPolicy.should_retry` 判停）。

    **刻意不是** `ConstraintError` —— `should_retry` 对 `ConstraintError` 恒返回 False（结构性
    错误），此处需其只按 `attempt < max_attempts` 判停，故用一个普通异常承载失败码。
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FaultChain:
    """constraints 重试链在 loop 执行接缝上的适配器（按 `tool_id` 可逆性隔离）。"""

    def __init__(
        self,
        provider: ToolProvider,
        policy: RetryPolicy,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._provider = provider
        self._policy = policy
        self._sleep = sleep
        self._reversible: frozenset[str] | None = None

    def _reversible_ids(self) -> frozenset[str]:
        """可逆工具 id 集合（惰性计算一次并缓存；只在失败路径调用）。"""
        if self._reversible is None:
            self._reversible = frozenset(
                tool.tool_id for tool in self._provider.active_tools() if tool.reversible
            )
        return self._reversible

    def wrap(self, act: ActFn) -> ActFn:
        """返回包裹 ``act`` 的执行接缝：执行类失败且工具可逆时退避重试。"""

        async def _wrapped(
            action: Action, trace_id: str, *, approved: bool = False
        ) -> ActionResult:
            result = await act(action, trace_id, approved=approved)
            if (
                action.is_terminal
                or not result.failed
                or result.error not in _RETRIABLE
                or action.tool_id not in self._reversible_ids()
            ):
                return result  # 直通：终止动作 / 成功 / 非白名单码 / 不可逆工具
            attempt = 1
            while self._policy.should_retry(attempt, RetriableToolFailureError(result.error)):
                await self._sleep(self._policy.backoff(attempt))
                attempt += 1
                result = await act(action, trace_id, approved=approved)
                if not result.failed:
                    return result
                if result.error not in _RETRIABLE:
                    break
            return result  # 耗尽：原样返回最后一次失败结果（不降级、不改码）

        return _wrapped


def build_fault_chain(
    provider: ToolProvider,
    *,
    max_attempts: int,
    base_delay: float = 0.5,
    jitter: float = 0.1,
) -> FaultChain:
    """构造 constraints→loop 重试链（尝试次数上界含首次调用）。"""
    return FaultChain(provider, RetryPolicy(max_attempts, base_delay, jitter))
