"""神兽独有神通（innate-skills，能力层）。

每兽一神通，以 Skill 契约落地并注册进全局 SkillLibrary，命名空间
``beast.<拼音>``（skill_id 三节：``beast.<拼音>.<skill>``）。runtime 调用
deferred（loop 只消费 ToolProvider，不接 SkillLibrary）；本模块只做
「定义 + 注册」，专属路由语义由 BeastSession 按 agent_id 前缀过滤候选。

对应规格：doc/openspec/specs/beast-mode/spec.md（Innate Skills and Dedicated Routing）
"""

from __future__ import annotations

from core.skills import Skill, SkillLibrary

from .registry import BeastRegistry


def build_innate_skills(registry: BeastRegistry) -> list[Skill]:
    """为 20 神兽各构造一枚独有神通 Skill（不注册）。"""
    return [
        Skill(
            skill_id=beast.innate_skill,
            description=f"{beast.title}独有神通：{beast.domain}",
            task_types=[beast.domain],
            preconditions=[],
            param_schema={},
            instructions=f"以{beast.title}之力执行重大任务：{beast.domain}",
            version="v1",
            status="active",
        )
        for beast in registry.all()
    ]


def register_innate_skills(library: SkillLibrary, registry: BeastRegistry) -> int:
    """把 20 神通注册进全局 SkillLibrary，返回注册条数。"""
    skills = build_innate_skills(registry)
    for skill in skills:
        library.register(skill)
    return len(skills)
