"""技能路由（SkillRouter）。

按任务类型匹配最合适技能，返回匹配度排序的 Top-K；无匹配回退通用流程，
记录未命中（供后续新技能沉淀）。

对应接口：doc/03-interfaces/skills-interface.md §4
"""

from __future__ import annotations

from core.memory import MemoryEntry, MemoryStore

from .library import SkillLibrary
from .models import Skill, SkillMatch


class SkillRouter:
    """技能路由：任务 → 匹配度排序的 Top-K 技能。"""

    def __init__(self, library: SkillLibrary, *, memory: MemoryStore | None = None) -> None:
        self._library = library
        self._memory = memory
        self.misses: list[str] = []

    def match(self, task: str, *, top_k: int = 3) -> list[SkillMatch]:
        """按任务类型匹配，返回匹配度排序的 Top-K；无匹配返回空列表并记录未命中。"""
        terms = _terms(task)
        scored = [
            SkillMatch(skill=skill, score=self._score(skill, terms))
            for skill in self._library.all_skills()
            if skill.status in ("active", "gray")
        ]
        scored = [m for m in scored if m.score > 0]
        scored.sort(key=lambda m: m.score, reverse=True)
        if not scored:
            self._record_miss(task)
        return scored[:top_k]

    # ---- 内部辅助 ----

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


def _terms(text: str) -> list[str]:
    return [t for t in text.lower().split() if t]
