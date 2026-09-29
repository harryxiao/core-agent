"""pet-library 单元测试（人格约束 + 角色库闭环 + pet.md 加载）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.pet.library import CharacterLibrary, Persona, load_persona, load_personas, parse_persona


def test_render_prompt_contains_persona_text() -> None:
    persona = Persona(name="小橘", species="猫", persona_text="慵懒但敏锐", traits=["安静"])
    prompt = persona.render_prompt()
    assert "小橘" in prompt
    assert "猫" in prompt
    assert "慵懒但敏锐" in prompt
    assert "安静" in prompt


def test_template_create_returns_clone() -> None:
    lib = CharacterLibrary()
    assert "cat" in lib.templates()
    cat = lib.create_from_template("cat")
    assert cat.name == "小橘"
    cat.traits.append("独立")
    assert "独立" not in lib.create_from_template("cat").traits


def test_register_custom() -> None:
    lib = CharacterLibrary()
    custom = Persona(name="自定", species="兔", persona_text="温顺", traits=["胆小"])
    lib.register_custom(custom)


def test_unknown_template_raises() -> None:
    with pytest.raises(KeyError):
        CharacterLibrary().create_from_template("dragon")


def test_export_import_roundtrip() -> None:
    lib = CharacterLibrary()
    persona = Persona(
        name="旺财",
        species="狗",
        persona_text="热情忠诚",
        traits=["热情", "忠诚"],
        preferences=["散步"],
    )
    assert lib.import_character(lib.export_character(persona)) == persona


def test_import_invalid_spec_raises() -> None:
    with pytest.raises(ValueError):
        CharacterLibrary().import_character({"name": "x"})


# ---- pet.md 加载（R9：多宠物 persona 文件） ----


_PET_MD = """\
name: 小橘
species: 猫
traits: 慵懒、敏锐
preferences: 晒太阳，蹭手
---
慵懒但敏锐，喜欢在主人工作时安静陪伴。
"""


def test_parse_persona_full() -> None:
    persona = parse_persona(_PET_MD, default_name="fallback")
    assert persona.name == "小橘"
    assert persona.species == "猫"
    assert persona.traits == ["慵懒", "敏锐"]
    assert persona.preferences == ["晒太阳", "蹭手"]
    assert "慵懒但敏锐" in persona.persona_text


def test_parse_persona_default_name() -> None:
    persona = parse_persona("species: 狗\n---\n忠诚", default_name="旺财")
    assert persona.name == "旺财"
    assert persona.species == "狗"
    assert persona.persona_text == "忠诚"


def test_load_persona_from_file(tmp_path: Path) -> None:
    path = tmp_path / "小橘.md"
    path.write_text(_PET_MD, encoding="utf-8")
    persona = load_persona(path)
    assert persona.name == "小橘"  # name 字段优先于文件名
    assert persona.species == "猫"


def test_load_persona_name_falls_back_to_stem(tmp_path: Path) -> None:
    path = tmp_path / "旺财.md"
    path.write_text("species: 狗\n---\n忠诚", encoding="utf-8")
    assert load_persona(path).name == "旺财"


def test_load_personas_directory(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("name: A\nspecies: 猫\n---\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("name: B\nspecies: 狗\n---\n", encoding="utf-8")
    personas = load_personas(tmp_path)
    assert sorted(personas) == ["a", "b"]
    assert personas["a"].name == "A"
    assert personas["b"].species == "狗"


def test_load_personas_empty_dir(tmp_path: Path) -> None:
    assert load_personas(tmp_path) == {}
