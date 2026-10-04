"""技能语义匹配（SkillMatcher）。

以 score 原语对**候选技能**逐条打分，供技能路由在词法无命中时兜底（0044）；
经注入的 :class:`DecisionRouter` 统一决策，不内联 JEV 调用。

score 原语只给「条目集单一分数」（无 per-item 分数，见 ADR-0047 决策 ③）→ K 个候选
即 K 次 ``decide()``。候选以 **dict 快照**传入，本模块**不 import skills**
（依赖方向与 ``Compactor`` / ``SopWriter`` 一致：两侧都不知道对方的类型）。

对应接口：doc/03-interfaces/judgment-interface.md §4.1
"""

from __future__ import annotations

from typing import Any

from .models import DecisionPrimitive, DecisionRequest
from .router import DecisionRouter


class SkillMatcher:
    """技能语义匹配：逐候选打分（打分失败/为 0 的候选略过，不产生伪命中）。"""

    def __init__(self, router: DecisionRouter) -> None:
        self._router = router

    def score(self, task: str, skills: list[dict[str, Any]]) -> dict[str, float]:
        """(任务文本, 候选技能快照) → {skill_id: 分值}；每候选一次 score 调用。"""
        scores: dict[str, float] = {}
        for skill in skills:
            value = self._score_one(task, skill)
            if value > 0:
                scores[skill["skill_id"]] = value
        return scores

    # ---- 内部辅助 ----

    def _score_one(self, task: str, skill: dict[str, Any]) -> float:
        """单候选打分；坏答案 / 调用失败 / 回退（0.0）一律返回 0.0。"""
        request = DecisionRequest(
            primitive=DecisionPrimitive.SCORE,
            state={"task": task},
            questions={"score": {"primitive": "score", "items": [skill]}},
            options=None,
            threshold=None,
        )
        try:
            return float(self._router.decide(request).answers["score"]["score"])
        except Exception:  # noqa: BLE001 — 逐候选跳过，坏答案不污染候选集
            return 0.0
