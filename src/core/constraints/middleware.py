"""中间件统一契约与洋葱管道（constraints）。

:class:`Middleware` 定义 before / after 两端；:class:`Pipeline` 按洋葱模型
执行：before 顺序 → 核心 → after 逆序；核心抛异常时逆序调用各中间件可选
``on_failure``（降级 / 回滚），首个返回非 None 的响应短路后续处理。

对应接口：doc/03-interfaces/constraints-interface.md §1
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from .models import ExecContext, ExecRequest, ExecResponse


class Middleware(Protocol):
    """中间件契约：name + before（输入侧）+ after（输出侧）。"""

    name: str

    def before(self, ctx: ExecContext, req: ExecRequest) -> ExecRequest:
        """输入侧处理：校验 / 熔断 / 重试。"""
        ...

    def after(self, ctx: ExecContext, resp: ExecResponse) -> ExecResponse:
        """输出侧处理：校验 / 回滚。"""
        ...


class Pipeline:
    """洋葱管道：before 顺序、after 逆序、失败逆序触发 on_failure。"""

    def execute(
        self,
        ctx: ExecContext,
        req: ExecRequest,
        middlewares: Sequence[Middleware],
        core: Callable[[ExecContext, ExecRequest], ExecResponse],
    ) -> ExecResponse:
        current = req
        for middleware in middlewares:
            current = middleware.before(ctx, current)
        try:
            resp = core(ctx, current)
        except Exception as exc:  # noqa: BLE001 — 失败需逆序触发 on_failure 降级/回滚
            fallback = self._on_failure(ctx, current, middlewares, exc)
            if fallback is not None:
                return fallback
            raise
        for middleware in reversed(middlewares):
            resp = middleware.after(ctx, resp)
        return resp

    def _on_failure(
        self,
        ctx: ExecContext,
        req: ExecRequest,
        middlewares: Sequence[Middleware],
        error: Exception,
    ) -> ExecResponse | None:
        """逆序触发中间件 on_failure，返回首个非 None 的降级/回滚响应。"""
        for middleware in reversed(middlewares):
            on_failure = getattr(middleware, "on_failure", None)
            if on_failure is not None:
                fallback = on_failure(ctx, req, error)
                if fallback is not None:
                    return fallback
        return None
