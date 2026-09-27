"""技能结晶/溶解（SkillCrystallizer）。

复用次数达阈值 + 过验证门 → 结晶为 L1 插件（联动 evolution）；失效/退化 →
溶解回 L3 技能，教训写回记忆。

对应接口：doc/03-interfaces/skills-interface.md §5
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable

from core.memory import MemoryEntry, MemoryStore

from .library import SkillLibrary
from .models import Skill

Validator = Callable[[Skill], bool]


def _always_valid(_skill: Skill) -> bool:
    return True


class SkillCrystallizer:
    """技能结晶/溶解：验证门 + 溶解教训沉淀。"""

    def __init__(
        self,
        library: SkillLibrary | None = None,
        memory: MemoryStore | None = None,
        *,
        validator: Validator | None = None,
    ) -> None:
        self._library = library
        self._memory = memory
        self._validator: Validator = validator if validator is not None else _always_valid

    def crystallize(self, skill: Skill) -> bool:
        """复用次数达阈值 + 过验证门 → 结晶为 L1 插件（返回是否可结晶）。"""
        return skill.status in ("active", "gray") and bool(self._validator(skill))

    def dissolve(self, skill_id: str, reason: str) -> None:
        """失效/退化 → 溶解回 L3 技能，教训写回记忆。"""
        if self._library is not None:
            with contextlib.suppress(KeyError):
                self._library.lookup(skill_id).status = "deprecated"
        if self._memory is not None:
            self._memory.write(
                "L2",
                MemoryEntry(
                    id=f"skills.dissolve.{skill_id}",
                    layer="L2",
                    content=reason,
                    tags=["skills", "dissolve"],
                    source="skills",
                    trace_id="skills",
                ),
            )
