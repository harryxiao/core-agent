"""skills 单元测试（对齐 §23 契约 + M2 验收锚点）。

覆盖：注册校验 / 前置条件检查 / 灰度与 A/B（B 退化回退）/ 路由 Top-K 与
未命中 / 结晶与溶解。
"""

from __future__ import annotations

import pytest

from core.memory import MemoryStore
from core.skills import (
    Skill,
    SkillCrystallizer,
    SkillError,
    SkillErrorCode,
    SkillLibrary,
    SkillRouter,
    VersionManager,
)

# ---- 注册校验 ----


def test_register_invalid_schema_rejected() -> None:
    lib = SkillLibrary()
    with pytest.raises(SkillError) as exc_info:
        lib.register(Skill(skill_id="s.x", description="", param_schema="not-a-dict"))
    assert exc_info.value.code is SkillErrorCode.INVALID_SKILL_SCHEMA


def test_register_empty_id_rejected() -> None:
    lib = SkillLibrary()
    with pytest.raises(SkillError) as exc_info:
        lib.register(Skill(skill_id="", description=""))
    assert exc_info.value.code is SkillErrorCode.INVALID_SKILL_SCHEMA


# ---- 检索 / 前置条件 ----


def test_lookup_and_domain() -> None:
    lib = SkillLibrary()
    s = Skill(
        skill_id="skills.data.summarize", description="summarize docs", task_types=["summarize"]
    )
    lib.register(s)
    assert lib.lookup("skills.data.summarize") is s
    assert lib.list_by_domain("data") == [s]


def test_check_preconditions() -> None:
    lib = SkillLibrary()
    s = Skill(skill_id="s.x", description="", preconditions=["auth"])
    assert lib.check_preconditions(s, {"auth": True}) is True
    assert lib.check_preconditions(s, {}) is False


# ---- 灰度 / A/B ----


def test_ab_test_b_degrades_reverts_to_stable() -> None:
    lib = SkillLibrary()
    skill_b = Skill(skill_id="s.x", description="", version="v2", status="gray")
    lib.register(skill_b)
    vm = VersionManager(library=lib, metrics=lambda sid, ver: 1.0 if ver == "v1" else 0.2)
    result = vm.ab_test("s.x", "v1", "v2")
    assert result.decision == "revert"
    assert result.winner == "v1"
    assert skill_b.status == "deprecated"
    assert vm.select("s.x", {}) == "v1"


def test_ab_test_b_wins_promotes() -> None:
    vm = VersionManager(metrics=lambda sid, ver: 0.5 if ver == "v1" else 1.0)
    result = vm.ab_test("s.x", "v1", "v2")
    assert result.decision == "promote"
    assert result.winner == "v2"


def test_select_gray_ratio() -> None:
    lib = SkillLibrary()
    lib.register(Skill(skill_id="s.x", description="", version="v1", status="active"))
    vm = VersionManager(library=lib, rng=lambda: 0.1)
    vm.promote("s.x", "v2", 0.5)
    assert vm.select("s.x", {}) == "v2"


def test_select_falls_back_to_current() -> None:
    lib = SkillLibrary()
    lib.register(Skill(skill_id="s.x", description="", version="v1", status="active"))
    vm = VersionManager(library=lib)
    assert vm.select("s.x", {}) == "v1"


# ---- 路由 ----


def test_router_matches_top_k() -> None:
    lib = SkillLibrary()
    lib.register(
        Skill(
            skill_id="skills.data.summarize",
            description="summarize text",
            task_types=["summarize"],
            status="active",
        )
    )
    lib.register(
        Skill(
            skill_id="skills.data.chart",
            description="make chart",
            task_types=["chart"],
            status="active",
        )
    )
    lib.register(Skill(skill_id="skills.other.xyz", description="unrelated", status="draft"))
    router = SkillRouter(lib)
    matches = router.match("please summarize the report")
    assert matches and matches[0].skill.skill_id == "skills.data.summarize"


def test_router_no_match_records_miss() -> None:
    lib = SkillLibrary()
    memory = MemoryStore()
    router = SkillRouter(lib, memory=memory)
    assert router.match("totally unrelated task") == []
    assert router.misses == ["totally unrelated task"]


# ---- 结晶 / 溶解 ----


def test_crystallize_requires_active_and_validator() -> None:
    s = Skill(skill_id="s.x", description="", status="active")
    c = SkillCrystallizer()  # 缺省 validator 恒真
    assert c.crystallize(s) is True
    s.status = "draft"
    assert c.crystallize(s) is False


def test_dissolve_marks_deprecated_and_writes_lesson() -> None:
    lib = SkillLibrary()
    memory = MemoryStore()
    s = Skill(skill_id="s.x", description="", status="active")
    lib.register(s)
    c = SkillCrystallizer(library=lib, memory=memory)
    c.dissolve("s.x", "退化原因")
    assert s.status == "deprecated"
    assert memory.read("") != []
