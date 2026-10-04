"""技能路由（SkillRouter）。

按任务类型匹配最合适技能，返回匹配度排序的 Top-K；无匹配回退通用流程，
记录未命中（供后续新技能沉淀）。词法匹配是 fast path（零模型调用）；
词法**全无命中**时经注入的语义打分器兜底（缺省不启用）。

对应接口：doc/03-interfaces/skills-interface.md §4
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.memory import MemoryEntry, MemoryStore

from .library import SkillLibrary
from .models import Skill, SkillMatch

# 语义打分器契约：(任务文本, 候选技能快照) → {skill_id: 分值}；缺省不启用（纯词法）。
# 快照为 dict（不含 skills 类型）——打分器实现（judgment 域）不必依赖本模块。
SkillScorer = Callable[[str, list[dict[str, Any]]], dict[str, float]]

# 语义分低于此值不采纳（否则任何任务都能挂上某条技能，技能块被灌水进 prompt）
_SEMANTIC_MIN_SCORE = 0.5


class SkillRouter:
    """技能路由：任务 → 匹配度排序的 Top-K 技能。"""

    def __init__(
        self,
        library: SkillLibrary,
        *,
        memory: MemoryStore | None = None,
        scorer: SkillScorer | None = None,
        threshold: float = _SEMANTIC_MIN_SCORE,
    ) -> None:
        self._library = library
        self._memory = memory
        self._scorer = scorer
        self._threshold = threshold
        self.misses: list[str] = []

    def match(self, task: str, *, top_k: int = 3) -> list[SkillMatch]:
        """按任务类型匹配，返回匹配度排序的 Top-K；无匹配返回空列表并记录未命中。

        词法命中即返回（fast path，零模型调用）；词法全无命中时才走语义兜底，
        语义有命中即视为命中（不记未命中）。
        """
        terms = terms_of(task)
        candidates = [s for s in self._library.all_skills() if s.status in ("active", "gray")]
        scored = [SkillMatch(skill=s, score=self._score(s, terms)) for s in candidates]
        scored = [m for m in scored if m.score > 0] or self._semantic(task, candidates)
        scored.sort(key=lambda m: m.score, reverse=True)
        if not scored:
            self._record_miss(task)
        return scored[:top_k]

    # ---- 内部辅助 ----

    def _semantic(self, task: str, candidates: list[Skill]) -> list[SkillMatch]:
        """语义兜底：逐候选打分，取达阈值者（打分器缺省/故障/低于阈值即空，等价纯词法）。"""
        if self._scorer is None:
            return []
        try:
            scores = self._scorer(task, [_snapshot(skill) for skill in candidates])
        except Exception:  # noqa: BLE001 — 打分器故障降级为词法，不中断路由
            return []
        return [
            SkillMatch(skill=skill, score=value)
            for skill in candidates
            if (value := scores.get(skill.skill_id, 0.0)) >= self._threshold
        ]

    def _score(self, skill: Skill, terms: list[str]) -> float:
        if not terms:
            return 0.0
        haystack = " ".join([skill.skill_id, skill.description, *skill.task_types]).lower()
        hits = sum(1 for t in terms if t in haystack)
        return hits / len(terms)

    def _record_miss(self, task: str) -> None:
        self.misses.append(task)
        if self._memory is None:
            return
        self._memory.write(
            "L2",
            MemoryEntry(
                id=f"skills.miss.{len(self.misses)}",
                layer="L2",
                content=f"路由未命中: {task}",
                tags=["skills", "miss"],
                source="skills",
                trace_id="skills",
            ),
        )


def _snapshot(skill: Skill) -> dict[str, Any]:
    """技能快照：供域外打分器消费的最小字段（不暴露 skills 类型）。"""
    return {
        "skill_id": skill.skill_id,
        "description": skill.description,
        "task_types": list(skill.task_types),
    }


def terms_of(text: str) -> list[str]:
    """任务/技能声明的词元（小写空白切分）：路由打分与 SOP 归组共用同一口径。"""
    return [t for t in text.lower().split() if t]
