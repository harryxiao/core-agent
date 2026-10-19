"""技能提炼确定性质量门与技能库字段上界（change 0255 / ADR-0246）。

覆盖：单步 / 超短 / 超长提炼不入库且清组、两步提炼照常发布、确定性门先于判定门、
逐字重复不入库、`SkillLibrary.register` 字段越界拒收且不覆盖既有技能。
"""

from __future__ import annotations

import itertools
import warnings
from typing import Any

import pytest

from core.skills import Skill, SkillError, SkillErrorCode, SkillLibrary, SopExtractor

_SEQ = itertools.count()


def _steps() -> list[str]:
    """真实行动序列形态（`tools.` 行首）；自增 nonce 代表不同执行轨迹。"""
    return [f"tools.echo（n={next(_SEQ)}）→ 结果"]


# ---- 确定性发布门 ----


def test_two_step_sop_publishes() -> None:
    """对照锚：满足确定性门的两步提炼照常以 `draft` 入库。"""
    lib = SkillLibrary()
    extractor = SopExtractor(lib, writer=lambda _prompt: "1. 准备输入\n2. 输出结果", threshold=1)

    skill = extractor.observe("task alpha", _steps())

    assert skill is not None and skill.status == "draft"
    assert lib.lookup(skill.skill_id) is skill


def test_single_step_sop_rejected_and_group_cleared() -> None:
    """单步提炼无复用价值 ⇒ 不入库 + 清组 + 留痕只报组键。"""
    lib = SkillLibrary()
    body = "1. 只做一个步骤而已"
    extractor = SopExtractor(lib, writer=lambda _prompt: body, threshold=2)

    assert extractor.observe("task alpha", _steps()) is None, "未达阈值不提炼"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert extractor.observe("task alpha", _steps()) is None, "单步 ⇒ 不入库"

    assert lib.all_skills() == [], "单步提炼不发布"
    assert len(caught) == 1, "确定性门未过留痕"
    text = str(caught[0].message)
    assert extractor._group_key("task alpha") in text, "留痕报组键"  # type: ignore[reportPrivateUsage]
    assert body not in text, "留痕绝不回显提炼正文"
    key = extractor._group_key("task alpha")  # type: ignore[reportPrivateUsage]
    assert extractor._samples.get(key, []) == [], "组已清空（免同批样本反复触发提炼）"  # type: ignore[reportPrivateUsage]
    assert extractor.observe("task alpha", _steps()) is None, "重新累积，不立即提炼"


def test_too_short_sop_rejected_and_group_cleared() -> None:
    """退化短文本（< 10 字符）⇒ 不入库 + 清组。"""
    lib = SkillLibrary()
    extractor = SopExtractor(lib, writer=lambda _prompt: "ok", threshold=2)

    assert extractor.observe("task alpha", _steps()) is None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert extractor.observe("task alpha", _steps()) is None

    assert lib.all_skills() == [], "超短提炼不发布"
    assert len(caught) == 1
    key = extractor._group_key("task alpha")  # type: ignore[reportPrivateUsage]
    assert extractor._samples.get(key, []) == [], "组已清空"  # type: ignore[reportPrivateUsage]
    assert extractor.observe("task alpha", _steps()) is None, "重新累积，不立即提炼"


def test_too_long_sop_rejected() -> None:
    """超长文本（> 4000 字符）⇒ 不入库。"""
    lib = SkillLibrary()
    body = "1. 步骤一\n2. " + "执行子步骤 " * 900  # > 4000 字符；不含密钥形态
    extractor = SopExtractor(lib, writer=lambda _prompt: body, threshold=1)

    assert extractor.observe("task alpha", _steps()) is None

    assert lib.all_skills() == [], "超长提炼不发布"


def test_deterministic_gate_runs_before_injected_gate() -> None:
    """确定性门先于判定门：形式不合格时判定门**不被调用**（零额外判定）。"""
    lib = SkillLibrary()
    seen: list[tuple[str, str]] = []

    def gate(task: str, sop: str) -> bool:
        seen.append((task, sop))
        return True

    extractor = SopExtractor(lib, writer=lambda _prompt: "1. 单步而已", threshold=1, gate=gate)

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        assert extractor.observe("task alpha", _steps()) is None

    assert seen == [], "确定性门先拦，判定门不执行"
    assert lib.all_skills() == []


def test_duplicate_instructions_not_published() -> None:
    """与库中任一技能 `instructions` 逐字相同 ⇒ 不入库（既有技能逐字不变）。"""
    lib = SkillLibrary()
    existing = Skill(
        skill_id="skills.data.summarize",
        description="summarize text",
        task_types=["report summarize"],
        instructions="1. 读输入\n2. 输出摘要",
        status="active",
    )
    lib.register(existing)
    extractor = SopExtractor(lib, writer=lambda _prompt: "1. 读输入\n2. 输出摘要", threshold=2)

    assert extractor.observe("task alpha", _steps()) is None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert extractor.observe("task alpha", _steps()) is None, "逐字重复 ⇒ 不入库"

    assert lib.all_skills() == [existing], "技能库条目数不变"
    assert lib.lookup(existing.skill_id).instructions == "1. 读输入\n2. 输出摘要"
    assert len(caught) == 1, "重复拦截留痕"
    key = extractor._group_key("task alpha")  # type: ignore[reportPrivateUsage]
    assert extractor._samples.get(key, []) == [], "组已清空"  # type: ignore[reportPrivateUsage]
    assert extractor.observe("task alpha", _steps()) is None, "重新累积，不立即提炼"


# ---- 技能库字段上界 ----


def _skill(**overrides: Any) -> Skill:
    fields: dict[str, Any] = {
        "skill_id": "skills.data.ok",
        "description": "ok",
        "task_types": ["t"],
        "preconditions": ["p"],
        "instructions": "1. 读\n2. 写",
    }
    fields.update(overrides)
    return Skill(**fields)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("skill_id", "s" * 121),
        ("description", "d" * 401),
        ("instructions", "i" * 4001),
        ("task_types", ["t" * 81]),
        ("task_types", [f"t{i}" for i in range(17)]),
        ("preconditions", ["p" * 201]),
        ("preconditions", [f"p{i}" for i in range(9)]),
    ],
)
def test_register_rejects_field_over_bound(field: str, value: object) -> None:
    """任一字段越界 ⇒ `INVALID_SKILL_SCHEMA`，库内容不变。"""
    lib = SkillLibrary()

    with pytest.raises(SkillError) as exc_info:
        lib.register(_skill(**{field: value}))

    assert exc_info.value.code is SkillErrorCode.INVALID_SKILL_SCHEMA
    assert lib.all_skills() == [], "越界技能不新增"


def test_register_over_bound_does_not_overwrite_existing() -> None:
    """同 id 的越界注册不覆盖既有技能（既有条目逐字不变）。"""
    lib = SkillLibrary()
    existing = _skill()
    lib.register(existing)

    with pytest.raises(SkillError):
        lib.register(_skill(instructions="i" * 4001))

    assert lib.lookup(existing.skill_id) is existing
    assert lib.lookup(existing.skill_id).instructions == "1. 读\n2. 写"


def test_register_within_bounds_unchanged() -> None:
    """对照锚：上界内的注册（含同 id 覆盖）语义逐字不变。"""
    lib = SkillLibrary()
    lib.register(_skill())

    replacement = _skill(description="new")
    lib.register(replacement)

    assert lib.lookup("skills.data.ok") is replacement
