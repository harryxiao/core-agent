"""宠物人格模型（pet-library）。

pet.md/prompt 设定角色/性格/喜好，行为与输出风格受人格约束（R9）；
实现 core.pet.core.PersonaLayer 基础属性层。

对应接口：doc/03-interfaces/pet-mode-interface.md §1（基础属性层）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast


@dataclass
class Persona:
    """宠物人格：角色/物种/性格/喜好 + pet.md 人格 prompt。"""

    name: str
    species: str
    persona_text: str
    traits: list[str] = field(default_factory=list[str])
    preferences: list[str] = field(default_factory=list[str])

    def render_prompt(self) -> str:
        """组合 pet.md 人格 prompt（角色/性格/喜好约束输出风格）。"""
        traits = "、".join(self.traits) if self.traits else "温和"
        likes = "、".join(self.preferences) if self.preferences else "无特别偏好"
        return (
            f"你是 {self.name}，一只{self.species}。\n"
            f"性格：{traits}。喜好：{likes}。\n"
            f"{self.persona_text}"
        )


def persona_from_record(data: dict[str, Any]) -> Persona:
    """从注册表快照重建人格（字段与 ``PetSession.snapshot()["persona"]`` 同构）。

    缺键取 dataclass 缺省值；未知键忽略（人格是描述性文本，无版本迁移面）。
    """
    return Persona(
        name=str(data.get("name", "")),
        species=str(data.get("species", "")),
        persona_text=str(data.get("persona_text", "")),
        traits=[str(item) for item in cast("list[Any]", data.get("traits") or [])],
        preferences=[str(item) for item in cast("list[Any]", data.get("preferences") or [])],
    )
