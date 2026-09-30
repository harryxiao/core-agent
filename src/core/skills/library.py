"""原子技能库（SkillLibrary）。

维护技能注册表 + 领域索引：注册时校验 schema（非法抛 INVALID_SKILL_SCHEMA），
前置条件不满足拒绝调用（返回 False 供调用方携带 PRECONDITION_FAILED）。

对应接口：doc/03-interfaces/skills-interface.md §2
"""

from __future__ import annotations

from typing import Any

from .errors import SkillError, SkillErrorCode
from .models import Skill


def _domain(skill_id: str) -> str:
    """从 "skills.<domain>.<name>" 提取领域段。"""
    parts = skill_id.split(".")
    return parts[1] if len(parts) > 1 else ""


class SkillLibrary:
    """原子技能库：注册 / 检索 / 前置条件检查。"""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self._domain_index: dict[str, list[str]] = {}

    def register(self, skill: Skill) -> None:
        """入库；schema 非法抛 INVALID_SKILL_SCHEMA。"""
        if not skill.skill_id:
            raise SkillError(SkillErrorCode.INVALID_SKILL_SCHEMA, "skill_id 不能为空")
        if not isinstance(skill.param_schema, dict):
            raise SkillError(
                SkillErrorCode.INVALID_SKILL_SCHEMA,
                f"技能 {skill.skill_id} param_schema 非法（须为 dict）",
            )
        self._skills[skill.skill_id] = skill
        self._domain_index.setdefault(_domain(skill.skill_id), []).append(skill.skill_id)

    def lookup(self, skill_id: str) -> Skill:
        """按 skill_id 精确检索。"""
        return self._skills[skill_id]

    def list_by_domain(self, domain: str) -> list[Skill]:
        """按领域列出技能。"""
        return [self._skills[sid] for sid in self._domain_index.get(domain, [])]

    def all_skills(self) -> list[Skill]:
        """返回全部已注册技能。"""
        return list(self._skills.values())

    def remove(self, skill_id: str) -> None:
        """卸载技能；不存在抛 KeyError（对齐 lookup）。"""
        self._skills.pop(skill_id)
        domain = _domain(skill_id)
        if domain in self._domain_index:
            self._domain_index[domain] = [
                sid for sid in self._domain_index[domain] if sid != skill_id
            ]

    def check_preconditions(self, skill: Skill, ctx: dict[str, Any]) -> bool:
        """前置条件不满足返回 False（PRECONDITION_FAILED）。"""
        return all(bool(ctx.get(p)) for p in skill.preconditions)
