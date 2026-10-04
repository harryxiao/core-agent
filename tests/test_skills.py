"""skills 单元测试（对齐 §23 契约 + M2 验收锚点）。

覆盖：注册校验 / 前置条件检查 / 灰度与 A/B（B 退化回退）/ 路由 Top-K 与
未命中 / 结晶与溶解。
"""

from __future__ import annotations

import pytest

from core.memory import MemoryStore
from core.plugin_registry import EffectTracker
from core.skills import (
    Skill,
    SkillCrystallizer,
    SkillError,
    SkillErrorCode,
    SkillLibrary,
    SkillRouter,
    SopExtractor,
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


def test_remove_skill_and_cleans_domain_index() -> None:
    lib = SkillLibrary()
    lib.register(Skill(skill_id="skills.data.summarize", description="summarize docs"))
    lib.remove("skills.data.summarize")
    assert lib.all_skills() == []
    assert lib.list_by_domain("data") == []


def test_remove_missing_raises_key_error() -> None:
    with pytest.raises(KeyError):
        SkillLibrary().remove("skills.data.nope")


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


# ---- SOP 提炼（0043） ----


def _writer(text: str = "1. 读输入\n2. 提炼要点\n3. 输出摘要"):
    """假提炼器：记录被提炼的任务+样本，返回固定 SOP 文本（不触网）。"""
    calls: list[str] = []

    def _write(prompt: str) -> str:
        calls.append(prompt)
        return text

    _write.calls = calls  # type: ignore[attr-defined]
    return _write


def _steps(tool: str = "tools.echo") -> list[str]:
    return [f'assistant: {{"tool_id": "{tool}", "args": {{"text": "x"}}}}', 'tool: {"data": "x"}']


def test_sop_extract() -> None:
    lib = SkillLibrary()
    writer = _writer()
    extractor = SopExtractor(lib, writer=writer, threshold=3)

    assert extractor.observe("summarize the report", _steps()) is None, "未达阈值不提炼"
    assert extractor.observe("summarize the report", _steps()) is None
    skill = extractor.observe("summarize the report", _steps())

    assert skill is not None, "第 3 次成功轨迹触发提炼"
    assert skill.status == "active", "维度1 低风险自动发布"
    assert skill.instructions.startswith("1. 读输入"), "instructions 承载 SOP 步骤"
    assert skill.task_types and "summarize" in skill.task_types[0], "task_types 为归组键"
    assert lib.lookup(skill.skill_id) is skill
    assert len(writer.calls) == 1  # type: ignore[attr-defined]
    assert "summarize the report" in writer.calls[0]  # type: ignore[attr-defined]

    matches = SkillRouter(lib).match("please summarize the report")
    assert matches and matches[0].skill.skill_id == skill.skill_id, "提炼产物可被路由命中"


def test_sop_extract_below_threshold_and_failures_not_counted() -> None:
    lib = SkillLibrary()
    extractor = SopExtractor(lib, writer=_writer(), threshold=3)

    for _ in range(5):
        assert extractor.observe("same task", _steps(), ok=False) is None
    assert lib.all_skills() == [], "失败轨迹不计入累积（不是 SOP）"

    assert extractor.observe("same task", _steps()) is None
    assert lib.all_skills() == []


def test_sop_extract_groups_by_existing_task_types() -> None:
    lib = SkillLibrary()
    lib.register(
        Skill(
            skill_id="skills.data.summarize",
            description="summarize text",
            task_types=["report summarize"],
            status="active",
        )
    )
    extractor = SopExtractor(lib, writer=_writer(), threshold=2)

    assert extractor.observe("summarize report", _steps()) is None
    skill = extractor.observe("summarize report", _steps())

    assert skill is not None
    assert skill.task_types == ["report summarize"], "复用已有 task_type 作组键"
    assert skill.skill_id != "skills.data.summarize", "提炼产物是独立新技能，不覆盖已有技能"


def test_sop_extract_without_writer_degrades() -> None:
    lib = SkillLibrary()
    extractor = SopExtractor(lib, threshold=1)

    assert extractor.observe("任何任务", _steps()) is None
    assert lib.all_skills() == [], "未注入 writer → 不累积、不提炼"


def test_sop_extract_empty_text_not_registered_and_samples_kept() -> None:
    lib = SkillLibrary()
    extractor = SopExtractor(lib, writer=_writer("   "), threshold=2)

    assert extractor.observe("task a", _steps()) is None
    assert extractor.observe("task a", _steps()) is None
    assert lib.all_skills() == [], "空提炼不入库（不写半成品）"

    extractor._writer = _writer("1. 步骤")  # type: ignore[assignment]
    assert extractor.observe("task a", _steps()) is not None, "样本保留，下轮可再提炼"


def test_sop_extract_is_reversible() -> None:
    tracker = EffectTracker()
    lib = SkillLibrary()
    extractor = SopExtractor(lib, writer=_writer(), threshold=1, effect_tracker=tracker)

    skill = extractor.observe("task a", _steps())
    assert skill is not None and lib.all_skills() == [skill]

    report = tracker.rollback("skills.extract")

    assert report.undo_failed == []
    assert lib.all_skills() == [], "按 trace 回滚 → 技能从库中移除"
    tracker.rollback("skills.extract")  # 重复回滚不报错（幂等 undo）


# ---- 语义路由（0044） ----


def _summarize_library() -> SkillLibrary:
    lib = SkillLibrary()
    lib.register(
        Skill(
            skill_id="skills.data.summarize",
            description="summarize text",
            task_types=["report summarize"],
            status="active",
        )
    )
    return lib


def _semantic(scores: dict[str, float], *, raises: bool = False):
    """假打分器：记录被评分的候选，返回预设分值（不触网）。"""
    calls: list[tuple[str, list[dict]]] = []

    def _score(task: str, skills: list[dict]) -> dict[str, float]:
        calls.append((task, skills))
        if raises:
            raise RuntimeError("打分器不可用")  # noqa: TRY003
        return scores

    _score.calls = calls  # type: ignore[attr-defined]
    return _score


def test_router_semantic_fallback_hits_on_lexical_miss() -> None:
    scorer = _semantic({"skills.data.summarize": 0.9})
    router = SkillRouter(_summarize_library(), scorer=scorer)

    matches = router.match("整理会议纪要")

    assert [m.skill.skill_id for m in matches] == ["skills.data.summarize"]
    assert matches[0].score == 0.9  # noqa: PLR2004
    assert router.misses == [], "语义命中视为命中，不记 miss"


def test_router_lexical_hit_skips_semantic() -> None:
    scorer = _semantic({"skills.data.summarize": 0.9})
    router = SkillRouter(_summarize_library(), scorer=scorer)

    matches = router.match("please summarize the report")

    assert matches and matches[0].skill.skill_id == "skills.data.summarize"
    assert scorer.calls == [], "词法 fast path：命中时不产生打分调用"  # type: ignore[attr-defined]


def test_router_without_scorer_keeps_lexical_miss() -> None:
    router = SkillRouter(_summarize_library())

    assert router.match("整理会议纪要") == []
    assert router.misses == ["整理会议纪要"]


def test_router_semantic_below_threshold_records_miss() -> None:
    router = SkillRouter(_summarize_library(), scorer=_semantic({"skills.data.summarize": 0.4}))

    assert router.match("整理会议纪要") == []
    assert router.misses == ["整理会议纪要"], "低于阈值不采纳 → 仍记 miss"


def test_router_semantic_scorer_failure_degrades_to_lexical() -> None:
    router = SkillRouter(_summarize_library(), scorer=_semantic({}, raises=True))

    assert router.match("整理会议纪要") == [], "打分器故障不得中断路由"
    assert router.misses == ["整理会议纪要"]


def test_router_semantic_scores_only_active_and_gray() -> None:
    lib = _summarize_library()
    lib.register(
        Skill(skill_id="skills.draft.x", description="draft", task_types=["x"], status="draft")
    )
    scorer = _semantic({"skills.data.summarize": 0.8, "skills.draft.x": 0.99})
    router = SkillRouter(lib, scorer=scorer)

    matches = router.match("整理会议纪要")

    payload = scorer.calls[0][1]  # type: ignore[attr-defined]
    assert [item["skill_id"] for item in payload] == ["skills.data.summarize"], "draft 不参与打分"
    assert [m.skill.skill_id for m in matches] == ["skills.data.summarize"]
