"""约束守卫（Guardrail）。

以 noul 原语做守卫判断（放行/拦截），供权限/约束决策点消费；经注入的
:class:`DecisionRouter` 统一决策，不内联 JEV 调用。

对应接口：doc/03-interfaces/judgment-interface.md §5
"""

from __future__ import annotations

from typing import Any

from .models import DecisionPrimitive, DecisionRequest, DecisionResult
from .router import DecisionRouter


class Guardrail:
    """noul 布尔判断：约束守卫决策点。"""

    def __init__(self, router: DecisionRouter) -> None:
        self._router = router

    def check(
        self, state: dict[str, Any], action: dict[str, Any], threshold: float | None = None
    ) -> DecisionResult:
        """以 noul 原语做守卫判断，返回放行/拦截结论（见 result.answers[id].noul）。"""
        request = DecisionRequest(
            primitive=DecisionPrimitive.NOUL,
            state=state,
            questions={"noul": {"primitive": "noul", "action": action}},
            options=None,
            threshold=threshold,
        )
        return self._router.decide(request)
