"""记忆压实评分（Compactor）。

以 score 原语对候选内容评分，供记忆压实保留/丢弃决策；经注入的
:class:`DecisionRouter` 统一决策，不内联 JEV 调用。

对应接口：doc/03-interfaces/judgment-interface.md §4
"""

from __future__ import annotations

from typing import Any

from .models import DecisionPrimitive, DecisionRequest, DecisionResult
from .router import DecisionRouter


class Compactor:
    """score 评分筛选：记忆压实决策点。"""

    def __init__(self, router: DecisionRouter) -> None:
        self._router = router

    def score(
        self, state: dict[str, Any], items: list[dict[str, Any]], threshold: float | None = None
    ) -> DecisionResult:
        """以 score 原语对候选内容评分，供记忆压实保留/丢弃决策。"""
        request = DecisionRequest(
            primitive=DecisionPrimitive.SCORE,
            state=state,
            questions={"score": {"primitive": "score", "items": items}},
            options=None,
            threshold=threshold,
        )
        return self._router.decide(request)
