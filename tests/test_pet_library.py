"""pet-library 单元测试（人格约束 + 角色库模板/自定义/导入导出闭环）。"""

from __future__ import annotations

import pytest

from core.pet_library import CharacterLibrary, Persona


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
