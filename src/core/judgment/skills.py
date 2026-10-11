"""技能语义匹配（SkillMatcher）与 SOP 自动质量门（SopGate）。

以 score 原语对**候选技能**逐条打分，供技能路由在词法无命中时兜底（0044）；
以 noul 原语判定**提炼产物是否可发布**（0198）。均经注入的 :class:`DecisionRouter`
统一决策，不内联 JEV 调用。

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


class SopGate:
    """SOP 发布前的**自动**质量门（0198 / ADR-0188）：noul 布尔判断。

    「该提炼产物是否可复用 / 可执行 / 非空泛」由判定原语作答 ⇒ 守红线「维度1 技能库/SOP
    **全自动**」（**不**引入人工确认）。判定**故障 / 缺答案 ⇒ 放行**（fail-open）：
    门是**新增**的刹车，不能让一次判定故障把「此前一直正常发布」的路径变成**静默不发布**。
    """

    def __init__(self, router: DecisionRouter) -> None:
        self._router = router

    def __call__(self, task: str, sop: str) -> bool:
        """(任务文本, 提炼正文) → 是否放行；判定故障 / 缺答案 ⇒ True（fail-open）。"""
        request = DecisionRequest(
            primitive=DecisionPrimitive.NOUL,
            state={"task": task},
            questions={
                "noul": {"primitive": "noul", "action": {"kind": "publish_sop", "sop": sop}}
            },
            options=None,
            threshold=None,
        )
        try:
            return bool(self._router.decide(request).answers["noul"]["noul"])
        except Exception:  # noqa: BLE001 — 判定故障按放行（不阻断发布）
            return True


def sop_gate_with(router: DecisionRouter) -> SopGate:
    """把 noul 原语适配为 SOP 提炼器的质量门契约（`(task, sop) -> bool`）。"""
    return SopGate(router)
