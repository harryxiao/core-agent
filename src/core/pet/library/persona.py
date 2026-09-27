"""宠物人格模型（pet-library）。

pet.md/prompt 设定角色/性格/喜好，行为与输出风格受人格约束（R9）；
实现 core.pet.core.PersonaLayer 基础属性层。

对应接口：doc/03-interfaces/pet-mode-interface.md §1（基础属性层）
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
