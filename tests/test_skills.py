"""skills 单元测试（对齐 §23 契约 + M2 验收锚点）。

覆盖：注册校验 / 前置条件检查 / 灰度与 A/B（B 退化回退）/ 路由 Top-K 与
未命中 / 结晶与溶解。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.memory import MemoryStore
from core.plugin_registry import EffectTracker
from core.skills import (
    Skill,
    SkillCrystallizer,
    SkillError,
    SkillErrorCode,
    SkillFeedback,
    SkillIterator,
    SkillLibrary,
    SkillRouter,
    SopExtractor,
    VersionManager,
    skill_hint,
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


# ---- draft 启用（E72 / change 0133）----

# 启用效应的 trace（与 ``skills.library._ACTIVATE_TRACE`` 同值：回滚按此 trace 分组）
_ACTIVATE_TRACE = "skills.activate"


def _draft_skill(skill_id: str = "skills.demo.greet") -> Skill:
    return Skill(skill_id=skill_id, description="greet 问候", task_types=["greet"], status="draft")


def test_draft_not_routed_until_activated() -> None:
    lib = SkillLibrary()
    lib.register(_draft_skill())
    router = SkillRouter(lib)
    assert router.match("greet") == [], "draft 不进候选集（放行集仍 active/gray）"
    lib.activate("skills.demo.greet")
    assert [m.skill.skill_id for m in router.match("greet")] == ["skills.demo.greet"]


def test_activate_is_idempotent_and_tracks_once() -> None:
    lib = SkillLibrary()
    lib.register(_draft_skill())
    tracker = EffectTracker()
    lib.activate("skills.demo.greet", effect_tracker=tracker)
    lib.activate("skills.demo.greet", effect_tracker=tracker)
    assert lib.lookup("skills.demo.greet").status == "active"
    assert len(tracker.audit(_ACTIVATE_TRACE)) == 1, "重复启用不重复登记效应"


def test_activate_unknown_skill_raises_key_error() -> None:
    lib = SkillLibrary()
    with pytest.raises(KeyError):
        lib.activate("skills.demo.nope")
    assert lib.all_skills() == [], "未知 id 不静默创建技能"


def test_activate_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "skills.json"
    lib = SkillLibrary(path=path)
    lib.register(_draft_skill())
    lib.activate("skills.demo.greet")
    assert SkillLibrary(path=path).lookup("skills.demo.greet").status == "active"


def test_activate_effect_rollback_restores_draft() -> None:
    lib = SkillLibrary()
    lib.register(_draft_skill())
    tracker = EffectTracker()
    lib.activate("skills.demo.greet", effect_tracker=tracker)
    tracker.rollback(_ACTIVATE_TRACE)
    assert lib.lookup("skills.demo.greet").status == "draft"


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


# ---- 未命中记录的唯一性与有界（E48-b） ----


def test_miss_id_survives_process_restart() -> None:
    """id 由任务内容派生：新进程（计数归零）不得覆盖既有会话的未命中记录。"""
    lib = SkillLibrary()
    memory = MemoryStore()

    first = SkillRouter(lib, memory=memory)
    first.match("整理会议纪要", session_id="s1")

    restarted = SkillRouter(lib, memory=memory)  # 模拟进程重启：misses 计数从零开始
    restarted.match("写一份周报", session_id="s1")

    ids = [e.id for e in memory.audit() if e.source == "skills"]
    assert len(ids) == 2, "同会话两条未命中不得互相覆盖（改前均落 skills.miss.s1.1）"  # noqa: PLR2004


def test_duplicate_miss_same_task_is_idempotent() -> None:
    """同一会话重复未命中**同一任务** ⇒ 幂等刷新同一条（未命中清单按任务去重，供沉淀）。"""
    memory = MemoryStore()
    router = SkillRouter(SkillLibrary(), memory=memory)

    router.match("整理会议纪要", session_id="s1")
    router.match("整理会议纪要", session_id="s1")

    assert len([e for e in memory.audit() if e.source == "skills"]) == 1


def test_miss_diagnostic_window_is_bounded() -> None:
    """未命中诊断窗口有界：长跑进程不得随任务数线性膨胀，且最近一条可查。"""
    router = SkillRouter(SkillLibrary())
    count = 500

    for i in range(count):
        router.match(f"totally unrelated task {i}")

    assert len(router.misses) < count, "诊断窗口应有界"
    assert router.misses[-1] == f"totally unrelated task {count - 1}"


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


# ---- 执行反馈 / 命中注入 / 迭代闭环（0045） ----

_SID = "skills.sop.deadbeef"


def _sop_library() -> SkillLibrary:
    lib = SkillLibrary()
    lib.register(
        Skill(
            skill_id=_SID,
            description="SOP：summarize report",
            task_types=["summarize report"],
            instructions="1. 读输入\n2. 输出摘要",
            status="active",
        )
    )
    return lib


def _iterator(
    lib: SkillLibrary,
    feedback: SkillFeedback,
    *,
    writer=None,  # noqa: ANN001 — 测试替身
    rng=None,  # noqa: ANN001 — 测试替身
    tracker: EffectTracker | None = None,
) -> SkillIterator:
    """注入确定性 rng 的 VersionManager（灰度分流可断言）。"""
    versions = VersionManager(
        lib,
        metrics=lambda skill_id, version: feedback.success_rate(skill_id, version),
        rng=rng if rng is not None else lambda: 1.0,
    )
    return SkillIterator(lib, feedback, writer=writer, versions=versions, tracker=tracker)


def _drafted(
    *,
    fails: int,
    oks: int,
    text: str = "1. 先读输入\n2. 再输出摘要",
    rng=None,  # noqa: ANN001
    tracker: EffectTracker | None = None,
) -> tuple[SkillLibrary, SkillFeedback, SkillIterator]:
    """技能已进入迭代：草稿 v2 已灰度（返回库/反馈/迭代器）。"""
    lib = _sop_library()
    feedback = SkillFeedback()
    for _ in range(fails):
        feedback.record_outcome(_SID, version="v1", ok=False)
    for _ in range(oks):
        feedback.record_outcome(_SID, version="v1", ok=True)
    it = _iterator(lib, feedback, writer=lambda prompt: text, rng=rng, tracker=tracker)
    assert it.consider(lib.lookup(_SID)) == "v2"
    return lib, feedback, it


def test_feedback_accumulates_per_version() -> None:
    feedback = SkillFeedback()
    feedback.record_hit(_SID, version="v1")
    feedback.record_outcome(_SID, version="v1", ok=True)
    feedback.record_outcome(_SID, version="v2", ok=False)

    assert feedback.stats(_SID, version="v1").hits == 1
    assert feedback.stats(_SID, version="v1").ok == 1
    assert feedback.stats(_SID, version="v2").fail == 1
    assert feedback.stats(_SID).total == 2  # noqa: PLR2004 — 不指定版本 → 各版本合计
    assert feedback.success_rate(_SID, "v1") == 1.0
    assert feedback.success_rate(_SID, "v2") == 0.0
    assert feedback.success_rate("skills.unknown", "v1") == 0.0, "无样本 → 0.0"


def test_skill_hint_truncates_instructions() -> None:
    hint = skill_hint(_SID, "v2", "步" * 500)

    assert hint["skill_id"] == _SID and hint["version"] == "v2"
    assert len(hint["instructions"]) == 400, "instructions 按上界截断"  # noqa: PLR2004
    assert skill_hint(_SID, "v1", "")["instructions"] == ""


def test_iterator_consider_creates_draft_and_gray() -> None:
    lib = _sop_library()
    feedback = SkillFeedback()
    for _ in range(3):
        feedback.record_outcome(_SID, version="v1", ok=False)
    it = _iterator(lib, feedback, writer=lambda prompt: "1. 改进步骤")

    assert it.consider(lib.lookup(_SID)) == "v2", "失败率达阈值 → 生成下一版"
    assert lib.lookup(_SID).version == "v1", "草稿不写回技能本体"


def test_iterator_consider_skips_below_samples() -> None:
    lib = _sop_library()
    feedback = SkillFeedback()
    calls: list[str] = []
    feedback.record_outcome(_SID, version="v1", ok=False)
    feedback.record_outcome(_SID, version="v1", ok=False)
    it = _iterator(lib, feedback, writer=lambda prompt: calls.append(prompt) or "x")

    assert it.consider(lib.lookup(_SID)) is None
    assert calls == [], "样本不足 → 不调用改写器"


def test_iterator_consider_skips_below_failure_rate() -> None:
    lib = _sop_library()
    feedback = SkillFeedback()
    for _ in range(3):
        feedback.record_outcome(_SID, version="v1", ok=True)
    calls: list[str] = []
    it = _iterator(lib, feedback, writer=lambda prompt: calls.append(prompt) or "x")

    assert it.consider(lib.lookup(_SID)) is None, "执行正常 → 不迭代"
    assert calls == []


def test_iterator_consider_without_writer_is_noop() -> None:
    lib = _sop_library()
    feedback = SkillFeedback()
    for _ in range(3):
        feedback.record_outcome(_SID, version="v1", ok=False)

    assert _iterator(lib, feedback).consider(lib.lookup(_SID)) is None, "未注入改写器 → 零调用"


def test_iterator_consider_empty_text_not_drafted() -> None:
    lib = _sop_library()
    feedback = SkillFeedback()
    for _ in range(3):
        feedback.record_outcome(_SID, version="v1", ok=False)
    it = _iterator(lib, feedback, writer=lambda prompt: "   ")

    assert it.consider(lib.lookup(_SID)) is None, "空改写文本不入草稿"
    assert it.resolve(lib.lookup(_SID)) == ("v1", "1. 读输入\n2. 输出摘要")


def test_iterator_resolve_splits_by_gray_ratio() -> None:
    lib, _, it = _drafted(fails=3, oks=0, rng=lambda: 0.0)

    assert it.resolve(lib.lookup(_SID)) == ("v2", "1. 先读输入\n2. 再输出摘要"), "命中灰度"

    lib2, _, it2 = _drafted(fails=3, oks=0, rng=lambda: 0.99)
    assert it2.resolve(lib2.lookup(_SID)) == ("v1", "1. 读输入\n2. 输出摘要"), "未命中灰度 → 原版"


def test_iterator_decide_promotes_better_version() -> None:
    tracker = EffectTracker()
    lib, feedback, it = _drafted(fails=2, oks=1, rng=lambda: 0.0, tracker=tracker)
    for _ in range(3):
        feedback.record_outcome(_SID, version="v2", ok=True)

    result = it.decide(lib.lookup(_SID))

    assert result is not None and result.decision == "promote"
    assert lib.lookup(_SID).version == "v2", "胜者成为当前版本"
    assert lib.lookup(_SID).instructions == "1. 先读输入\n2. 再输出摘要"

    tracker.rollback("skills.iterate")
    assert lib.lookup(_SID).version == "v1", "回滚恢复原版本"
    assert lib.lookup(_SID).instructions == "1. 读输入\n2. 输出摘要"


def test_iterator_decide_discards_worse_version() -> None:
    lib, feedback, it = _drafted(fails=3, oks=2, rng=lambda: 0.0)
    for _ in range(2):
        feedback.record_outcome(_SID, version="v2", ok=False)
    feedback.record_outcome(_SID, version="v2", ok=True)

    result = it.decide(lib.lookup(_SID))

    assert result is not None and result.decision == "revert"
    skill = lib.lookup(_SID)
    assert (skill.version, skill.status) == ("v1", "active"), "退化只丢草稿，技能不弃用"
    assert skill.instructions == "1. 读输入\n2. 输出摘要"


def test_iterator_decide_requires_both_versions_sampled() -> None:
    lib, _, it = _drafted(fails=3, oks=0, rng=lambda: 0.0)

    assert it.decide(lib.lookup(_SID)) is None, "草稿无样本 → 不定夺"
    assert lib.lookup(_SID).version == "v1"


# ---- 技能态持久化（0050） ----


def _sop(lib: SkillLibrary, path: Path) -> SopExtractor:
    """提炼器桩：writer 固定返回一段 SOP 文本，阈值 3（覆盖「样本跨进程累积」）。"""
    return SopExtractor(
        lib,
        writer=lambda _prompt: "1. 读输入\n2. 输出摘要",
        threshold=3,
        path=path,
    )


def test_library_persists_across_restart(tmp_path) -> None:
    path = tmp_path / "skills.json"
    lib = SkillLibrary(path=path)
    lib.register(
        Skill(
            skill_id="skills.sop.x",
            description="SOP：x",
            task_types=["x"],
            instructions="1. 读输入。",
            version="v2",
            status="active",
        )
    )

    revived = SkillLibrary(path=path).lookup("skills.sop.x")

    assert (revived.version, revived.status, revived.instructions) == (
        "v2",
        "active",
        "1. 读输入。",
    ), "重启后技能全字段恢复"


def test_feedback_persists_across_restart(tmp_path) -> None:
    path = tmp_path / "skill-feedback.json"
    feedback = SkillFeedback(path=path)
    feedback.record_hit("s.x", version="v1")
    feedback.record_outcome("s.x", version="v1", ok=True)
    feedback.record_outcome("s.x", version="v1", ok=False)

    revived = SkillFeedback(path=path).stats("s.x", version="v1")

    assert (revived.hits, revived.ok, revived.fail) == (1, 1, 1), "重启后计数恢复"


def test_sop_samples_persist_across_restart(tmp_path) -> None:
    path = tmp_path / "sop-samples.json"
    lib = SkillLibrary()
    first = _sop(lib, path)
    assert first.observe("读文档并摘要", ["step1"]) is None, "不足阈值不提炼"

    # 模拟进程重启：同一路径重建，样本应从 1 条续起（再提交 2 条即达阈值 3）
    revived_lib = SkillLibrary()
    second = _sop(revived_lib, path)
    second.observe("读文档并摘要", ["step2"])
    skill = second.observe("读文档并摘要", ["step3"])

    assert skill is not None, "样本跨重启累积，达阈值即提炼"
    assert revived_lib.lookup(skill.skill_id) is skill


def test_version_state_persists_across_restart(tmp_path) -> None:
    path = tmp_path / "skill-versions.json"
    lib = SkillLibrary()
    lib.register(Skill(skill_id="s.x", description="x", version="v1"))
    manager = VersionManager(lib, metrics=lambda _sid, ver: 1.0 if ver == "v1" else 0.0, path=path)
    manager.ab_test("s.x", "v1", "v2")

    revived = VersionManager(lib, path=path)

    assert revived.select("s.x", {}) == "v1", "重启后 A/B 胜者仍生效"

    gray_path = tmp_path / "skill-gray.json"
    gray = VersionManager(lib, path=gray_path)
    gray.promote("s.x", "v9", 1.0)
    assert VersionManager(lib, path=gray_path).select("s.x", {}) == "v9", "重启后灰度仍生效"


def test_no_path_means_pure_memory(tmp_path) -> None:
    lib = SkillLibrary()
    lib.register(Skill(skill_id="s.x", description="x"))
    feedback = SkillFeedback()
    feedback.record_outcome("s.x", version="v1", ok=True)
    _sop(lib, path=None).observe("t", ["step"])  # type: ignore[arg-type]  # 显式传 None
    VersionManager(lib).promote("s.x", "v2", 0.5)

    assert list(tmp_path.iterdir()) == [], "未注入路径 → 不产生任何落盘文件"


def test_corrupt_state_degrades_to_empty(tmp_path) -> None:
    path = tmp_path / "skills.json"
    path.write_text("{ not json", encoding="utf-8")

    lib = SkillLibrary(path=path)
    assert lib.all_skills() == [], "损坏落盘 → 空态启动（不抛异常）"

    lib.register(Skill(skill_id="s.x", description="x"))
    assert SkillLibrary(path=path).all_skills() != [], "后续写入覆盖损坏文件"
