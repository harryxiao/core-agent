"""技能排序接历史成功率因子（change 0058 / 账本 A7）。

证明规格自述的复合匹配度（`SkillMatch.score` = 语义 + 历史成功率）在生产真实成立，
且**加权只改排序、不改命中判定**：阈值仍判原始语义分，冷启动不惩罚新技能，
有样本时全失败技能仍保留一半排序分（下限，防「一次失败即永不入选」的正反馈）。
"""

from __future__ import annotations

import pytest

from core.configuration import ConfigManager
from core.runtime import build_runtime
from core.skills import Skill, SkillFeedback, SkillLibrary, SkillRouter

_QX_TASK = "架构设计 / 蓝图与骨架生成"  # 与 beast.qinglong 神通的 task_types 逐词元重合


def _write_config(tmp_path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n"
        "  reasoning_effort: low\n",
        encoding="utf-8",
    )
    return str(cfg)


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))


def _skill(skill_id: str, task_types: list[str]) -> Skill:
    return Skill(
        skill_id=skill_id,
        description=f"技能 {skill_id}",
        task_types=task_types,
        preconditions=[],
        param_schema={},
        instructions="按流程执行",
        status="active",
    )


def _library_with_twins() -> SkillLibrary:
    """两个**基础分相同**的技能（词法命中率同为 1.0）。"""
    library = SkillLibrary()
    library.register(_skill("demo.alpha", ["部署发布 流程"]))
    library.register(_skill("demo.beta", ["部署发布 流程"]))
    return library


_TASK = "部署发布 流程"


def _scores(router: SkillRouter, task: str = _TASK) -> dict[str, float]:
    return {m.skill.skill_id: m.score for m in router.match(task, top_k=10)}


def _ranked(router: SkillRouter, task: str = _TASK) -> list[str]:
    return [m.skill.skill_id for m in router.match(task, top_k=10)]


# ---- 因子口径 ----


def test_cold_start_does_not_penalize_new_skills() -> None:
    """无样本 → 因子 1.0：排序分 == 基础分（与未接反馈时一致）。"""
    library = _library_with_twins()
    baseline = _scores(SkillRouter(library))
    with_feedback = _scores(SkillRouter(library, feedback=SkillFeedback()))
    assert baseline == with_feedback
    assert baseline and all(v == pytest.approx(1.0) for v in baseline.values())


def test_success_rate_reweights_ordering() -> None:
    """基础分相同：全成功 > 全失败，且全失败仍返回（下限保证不为零）。"""
    library = _library_with_twins()
    feedback = SkillFeedback()
    for _ in range(3):
        feedback.record_outcome("demo.alpha", version="v1", ok=True)
        feedback.record_outcome("demo.beta", version="v1", ok=False)

    ranked = _ranked(SkillRouter(library, feedback=feedback))
    assert ranked == ["demo.alpha", "demo.beta"]  # 全成功排前
    scores = _scores(SkillRouter(library, feedback=feedback))
    assert scores["demo.alpha"] == pytest.approx(1.0)  # 全成功不打折
    assert scores["demo.beta"] == pytest.approx(0.5)  # 全失败打对折（下限）
    assert scores["demo.beta"] > 0  # 仍可被再次选中并翻盘


def test_partial_success_scales_between_floor_and_one() -> None:
    library = SkillLibrary()
    library.register(_skill("demo.gamma", ["部署发布 流程"]))
    feedback = SkillFeedback()
    feedback.record_outcome("demo.gamma", version="v1", ok=True)
    feedback.record_outcome("demo.gamma", version="v1", ok=False)
    scores = _scores(SkillRouter(library, feedback=feedback))
    assert scores["demo.gamma"] == pytest.approx(0.75)  # 50% 成功率 → 0.75


def test_weights_are_per_version() -> None:
    """统计按技能**当前版本**取：别的版本的历史不参与排序。"""
    library = SkillLibrary()
    library.register(_skill("demo.delta", ["部署发布 流程"]))
    feedback = SkillFeedback()
    feedback.record_outcome("demo.delta", version="v0", ok=False)  # 旧版本的历史
    scores = _scores(SkillRouter(library, feedback=feedback))
    assert scores["demo.delta"] == pytest.approx(1.0)  # 当前版本无样本 → 因子 1.0


# ---- 阈值不受加权影响（命中判定用基础分） ----


def _library_with_one() -> SkillLibrary:
    library = SkillLibrary()
    library.register(_skill("demo.semantic", ["summarize report"]))
    return library


def test_weighting_does_not_change_hit_decision() -> None:
    """语义分达阈值但历史全失败 → 仍被返回（阈值判原始语义分，加权只缩放 score）。"""
    feedback = SkillFeedback()
    feedback.record_outcome("demo.semantic", version="v1", ok=False)
    router = SkillRouter(
        _library_with_one(),
        scorer=lambda task, skills: {"demo.semantic": 0.9},
        feedback=feedback,
    )
    hits = router.match("完全不相交的任务文本")
    assert [m.skill.skill_id for m in hits] == ["demo.semantic"]
    assert hits[0].score == pytest.approx(0.45)  # 0.9 × 0.5，仍返回
    assert router.misses == []  # 命中（不记 miss）


def test_semantic_hit_keeps_raw_score_when_cold() -> None:
    """冷启动语义命中：score 保持原始语义分（既有场景 `score=0.9` 不变）。"""
    router = SkillRouter(
        _library_with_one(),
        scorer=lambda task, skills: {"demo.semantic": 0.9},
        feedback=SkillFeedback(),
    )
    assert router.match("完全不相交的任务文本")[0].score == pytest.approx(0.9)


# ---- 组合根接线 ----


def test_build_runtime_injects_shared_feedback(runtime) -> None:
    """组合根把**同一个** SkillFeedback 实例注入路由与迭代器（单一真源）。"""
    assert runtime.skill_router._feedback is runtime.skill_feedback  # noqa: SLF001 — 接线断言
    assert runtime.skill_iterator._feedback is runtime.skill_feedback  # noqa: SLF001


def test_production_router_reflects_outcomes(runtime) -> None:
    """端到端：写进组合根反馈的成败，立刻改变生产路由的排序分。"""
    skill_id = "beast.qinglong.blueprint"
    hits = runtime.skill_router.match(_QX_TASK, domain="beast.qinglong", top_k=10)
    assert {m.skill.skill_id: m.score for m in hits}[skill_id] == pytest.approx(1.0)  # 冷启动

    runtime.skill_feedback.record_outcome(skill_id, version="v1", ok=False)
    hits = runtime.skill_router.match(_QX_TASK, domain="beast.qinglong", top_k=10)
    assert {m.skill.skill_id: m.score for m in hits}[skill_id] == pytest.approx(0.5)  # 全失败打对折
