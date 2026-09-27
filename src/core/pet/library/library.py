"""宠物角色库（pet-library）。

预置角色模板 + 自定义 + 导入/导出闭环（R10）。

对应接口：doc/03-interfaces/pet-mode-interface.md §1（角色库）
"""

from __future__ import annotations

from typing import Any, cast

from .persona import Persona

# 预置角色模板（物种/性格/喜好/pet.md 人格）。
_PRESET_TEMPLATES = {
    "cat": Persona(
        name="小橘",
        species="猫",
        persona_text="慵懒但敏锐，喜欢在主人工作时安静陪伴。",
        traits=["慵懒", "敏锐", "安静"],
        preferences=["晒太阳", "被抚摸"],
    ),
    "dog": Persona(
        name="旺财",
        species="狗",
        persona_text="热情忠诚，喜欢主动帮主人跑腿探索。",
        traits=["热情", "忠诚", "好奇"],
        preferences=["散步", "接飞盘"],
    ),
}


class CharacterLibrary:
    """宠物角色库：模板创建 / 自定义 / 导入导出。"""

    def __init__(self, templates: dict[str, Persona] | None = None) -> None:
        self._templates = dict(templates) if templates is not None else dict(_PRESET_TEMPLATES)
        self._custom: dict[str, Persona] = {}

    def templates(self) -> list[str]:
        """当前可用模板名（排序稳定）。"""
        return sorted(self._templates)

    def create_from_template(self, name: str) -> Persona:
        """从预置模板创建宠物（返回副本，避免共享状态）。"""
        if name not in self._templates:
            raise KeyError(f"未知角色模板: {name}")  # noqa: TRY003
        return _clone(self._templates[name])

    def register_custom(self, persona: Persona) -> None:
        """注册自定义角色。"""
        self._custom[persona.name] = persona

    def export_character(self, persona: Persona) -> dict[str, Any]:
        """导出角色定义为可序列化字典。"""
        return {
            "name": persona.name,
            "species": persona.species,
            "persona_text": persona.persona_text,
            "traits": list(persona.traits),
            "preferences": list(persona.preferences),
        }

    def import_character(self, spec: dict[str, Any]) -> Persona:
        """从字典导入角色定义；非法输入抛 ValueError。"""
        name = spec.get("name")
        species = spec.get("species")
        persona_text = spec.get("persona_text")
        if (
            not isinstance(name, str)
            or not isinstance(species, str)
            or not isinstance(persona_text, str)
        ):
            raise ValueError(  # noqa: TRY003, TRY004
                "角色定义格式非法：name/species/persona_text 须为字符串"
            )
        return Persona(
            name=name,
            species=species,
            persona_text=persona_text,
            traits=_str_list(spec.get("traits")),
            preferences=_str_list(spec.get("preferences")),
        )


def _clone(persona: Persona) -> Persona:
    return Persona(
        name=persona.name,
        species=persona.species,
        persona_text=persona.persona_text,
        traits=list(persona.traits),
        preferences=list(persona.preferences),
    )


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in cast("list[object]", value)]
