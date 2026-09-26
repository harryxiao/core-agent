"""容错中间件（constraints）：熔断 / 重试 / 降级 / 回滚。

- :class:`CircuitBreaker`：连续失败熔断，冷却后半开试探。
- :class:`RetryPolicy`：幂等操作指数退避重试。
- :class:`Fallback`：失败降级到备用 / 简化路径。
- :class:`Rollback`：复用 :class:`~core.plugin_registry.EffectTracker` 撤销本轮副作用。

对应接口：doc/03-interfaces/constraints-interface.md §3 / §4 / §5
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from core.plugin_registry import EffectTracker

from .errors import ConstraintError, ConstraintErrorCode
from .middleware import Middleware
from .models import ExecContext, ExecRequest, ExecResponse

_CLOSED = "CLOSED"
_OPEN = "OPEN"
_HALF_OPEN = "HALF_OPEN"


class CircuitBreaker(Middleware):
    """熔断器：CLOSED → (连续 N 失败) → OPEN → (冷却后) → HALF_OPEN 试探。"""

    name = "constraints.circuit_breaker"

    def __init__(self, failure_threshold: int = 5, cooldown_s: float = 30.0) -> None:
        self._threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._failures = 0
        self._state = _CLOSED
        self._opened_at = 0.0

    @property
    def state(self) -> str:
        if self._state == _OPEN and time.monotonic() - self._opened_at >= self._cooldown_s:
            self._state = _HALF_OPEN
        return self._state

    def before(self, ctx: ExecContext, req: ExecRequest) -> ExecRequest:
        if self.state == _OPEN:
            raise ConstraintError(ConstraintErrorCode.CIRCUIT_OPEN, "熔断器已打开，快速失败")
        return req

    def after(self, ctx: ExecContext, resp: ExecResponse) -> ExecResponse:
        return resp

    def record_result(self, success: bool) -> None:
        """成功清零 / 失败计数；连续 N 次失败 → OPEN。"""
        if self.state == _HALF_OPEN:
            if success:
                self._failures = 0
                self._state = _CLOSED
            else:
                self._state = _OPEN
                self._opened_at = time.monotonic()
            return
        if success:
            self._failures = 0
            return
        self._failures += 1
        if self._failures >= self._threshold:
            self._state = _OPEN
            self._opened_at = time.monotonic()


class RetryPolicy(Middleware):
    """幂等操作重试：仅可重试错误进入重试，指数退避 + 抖动。"""

    name = "constraints.retry_policy"

    def __init__(self, max_attempts: int = 3, base_delay: float = 0.5, jitter: float = 0.1) -> None:
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._jitter = jitter

    def before(self, ctx: ExecContext, req: ExecRequest) -> ExecRequest:
        return req

    def after(self, ctx: ExecContext, resp: ExecResponse) -> ExecResponse:
        return resp

    def should_retry(self, attempt: int, error: Exception) -> bool:
        """仅未超限且错误可重试（非结构性 :class:`ConstraintError`）时重试。"""
        return attempt < self._max_attempts and not isinstance(error, ConstraintError)

    def backoff(self, attempt: int) -> float:
        """指数退避 + 抖动（秒），封顶 8 秒。"""
        base = min(self._base_delay * (2 ** (attempt - 1)), 8.0)
        return base + random.uniform(0.0, self._jitter)


class Fallback(Middleware):
    """失败降级：核心抛异常时用备用路径产出一个结果。"""

    name = "constraints.fallback"

    def __init__(self, fallback_fn: Callable[[ExecContext, ExecRequest], ExecResponse]) -> None:
        self._fallback_fn = fallback_fn

    def before(self, ctx: ExecContext, req: ExecRequest) -> ExecRequest:
        return req

    def after(self, ctx: ExecContext, resp: ExecResponse) -> ExecResponse:
        return resp

    def on_failure(self, ctx: ExecContext, req: ExecRequest, error: Exception) -> ExecResponse:
        return self._fallback_fn(ctx, req)


class Rollback(Middleware):
    """失败回滚：撤销本轮 trace 下的全部可逆副作用。"""

    name = "constraints.rollback"

    def __init__(self, tracker: EffectTracker) -> None:
        self._tracker = tracker

    def before(self, ctx: ExecContext, req: ExecRequest) -> ExecRequest:
        return req

    def after(self, ctx: ExecContext, resp: ExecResponse) -> ExecResponse:
        return resp

    def on_failure(self, ctx: ExecContext, req: ExecRequest, error: Exception) -> ExecResponse:
        report = self._tracker.rollback(ctx.trace_id)
        if report.undo_failed:
            raise ConstraintError(
                ConstraintErrorCode.ROLLBACK_FAILED, f"回滚失败: {report.undo_failed}"
            )
        return ExecResponse(ok=False, error=str(error), data=None)
