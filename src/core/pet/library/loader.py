"""pet.md 人格文件加载（pet-library）。

每只宠物一个 `<name>.md`，声明角色/物种/性格特征/喜好 + 人格正文；
解析为 Persona 注入 PetSession，宠物行为/输出风格受其约束（R9）。

对应接口：doc/03-interfaces/pet-mode-interface.md §2
"""

from __future__ import annotations

from pathlib import Path

from .persona import Persona


def load_persona(path: Path) -> Persona:
    """从单个 pet.md 文件加载人格；name 缺省取文件名（去 .md）。"""
    return parse_persona(path.read_text(encoding="utf-8"), default_name=path.stem)


def parse_persona(text: str, *, default_name: str = "") -> Persona:
    """解析 pet.md 文本为 Persona。

    格式（键值行 + ``---`` 分隔 + 人格正文）：:

        name: 小橘
        species: 猫
        traits: 慵懒、敏锐
        preferences: 晒太阳
        ---
        慵懒但敏锐，喜欢在主人工作时安静陪伴。

    ``---`` 之后（或首个非键值行之后）的文本为 persona_text；``traits`` /
    ``preferences`` 按 ``、，,；;`` 分隔。
    """
    name = default_name
    species = ""
    traits: list[str] = []
    preferences: list[str] = []
    body: list[str] = []
    in_body = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "---":
            in_body = True
            continue
        if in_body or ":" not in line:
            body.append(line)
            in_body = True
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "name" and value:
            name = value
            continue
        if key == "species" and value:
            species = value
            continue
        if key == "traits":
            traits = _split_list(value)
            continue
        if key == "preferences":
            preferences = _split_list(value)
            continue
        body.append(line)
        in_body = True
    persona_text = "\n".join(body).strip()
    return Persona(
        name=name,
        species=species,
        persona_text=persona_text,
        traits=traits,
        preferences=preferences,
    )


def load_personas(directory: Path) -> dict[str, Persona]:
    """加载目录下全部 `<name>.md` 为 Persona（key=name，排序稳定）。"""
    result: dict[str, Persona] = {}
    if not directory.is_dir():
        return result
    for path in sorted(directory.glob("*.md")):
        result[path.stem] = load_persona(path)
    return result


def _split_list(value: str) -> list[str]:
    """按常见分隔符拆分列表字段（、，,；;），保留含空格的多词项。"""
    for sep in ("、", "，", ",", "；", ";"):
        value = value.replace(sep, "、")
    return [p.strip() for p in value.split("、") if p.strip()]
