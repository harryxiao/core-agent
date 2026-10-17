"""SOP 技能退役（change 0205 / ADR-0195 / 台账 E142）单元 + 配置测试。

覆盖：`SkillLibrary.deprecate`（置状态 + 落盘 + 幂等 + 未知 id + 可逆）；`SkillIterator` 连续
A/B 退化达阈自动退役（一次提升归零）；**缺省关**零回归锚；退役技能退出路由；**粘性防复活**
（SOP 重抽不复活）；配置三面齐备 + 组合根接线。
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from core.configuration import ConfigManager, config_specs
from core.plugin_registry import EffectTracker
from core.runtime import build_runtime
from core.skills import (
    RETIRE_AFTER_DEGRADATIONS,
    Skill,
    SkillFeedback,
    SkillIterator,
    SkillLibrary,
    SkillRouter,
    SopExtractor,
    VersionManager,
)
from core.skills.sop import _skill_id_for

_SID = "skills.sop.demo"
_TASK = "summarize report"
_RETIRE = RETIRE_AFTER_DEGRADATIONS
_MIN_SAMPLES = 3  # 迭代器默认样本下限（草稿须达此才参与 A/B 定夺）

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _skill(skill_id: str = _SID, status: str = "active") -> Skill:
    return Skill(
        skill_id=skill_id,
        description="SOP：summarize report",
        task_types=[_TASK],
        instructions="1. 读输入\n2. 输出摘要",
        status=status,
    )


def _library(path: Path | None = None) -> SkillLibrary:
    lib = SkillLibrary(path=path)
    lib.register(_skill())
    return lib


def _iterator(
    lib: SkillLibrary,
    feedback: SkillFeedback,
    *,
    retire_after: int | None = None,
    tracker: EffectTracker | None = None,
) -> SkillIterator:
    versions = VersionManager(
        lib,
        metrics=lambda skill_id, version: feedback.success_rate(skill_id, version),
        rng=lambda: 0.0,
    )
    return SkillIterator(
        lib,
        feedback,
        writer=lambda prompt: "1. 改进步骤\n2. 再输出",
        versions=versions,
        tracker=tracker,
        retire_after=retire_after,
    )


def _degrading_feedback() -> SkillFeedback:
    """当前版本 v1 失败率达阈值（可触发迭代起草）。"""
    feedback = SkillFeedback()
    for _ in range(3):
        feedback.record_outcome(_SID, version="v1", ok=False)
    for _ in range(2):
        feedback.record_outcome(_SID, version="v1", ok=True)
    return feedback


def _degrade(lib: SkillLibrary, feedback: SkillFeedback, it: SkillIterator) -> None:
    """触发一次迭代 → 一次 A/B **退化**定夺（草稿比当前版本差）。"""
    draft = it.consider(lib.lookup(_SID))
    assert draft is not None, "失败率达阈 → 起草"
    while feedback.stats(_SID, version=draft).total < _MIN_SAMPLES:
        feedback.record_outcome(_SID, version=draft, ok=False)
    result = it.decide(lib.lookup(_SID))
    assert result is not None and result.decision == "revert"


def _promote(lib: SkillLibrary, feedback: SkillFeedback, it: SkillIterator) -> None:
    """触发一次 A/B **提升**定夺（草稿成功率高于当前版本）。"""
    current = lib.lookup(_SID).version
    draft = it.consider(lib.lookup(_SID))
    assert draft is not None
    while feedback.success_rate(_SID, draft) <= feedback.success_rate(_SID, current):
        feedback.record_outcome(_SID, version=draft, ok=True)
    result = it.decide(lib.lookup(_SID))
    assert result is not None and result.decision == "promote"


# ---- SkillLibrary.deprecate ----


def test_deprecate_sets_status_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "skills.json"
    lib = _library(path)

    returned = lib.deprecate(_SID)

    assert returned.status == "deprecated"
    assert SkillLibrary(path).lookup(_SID).status == "deprecated", "落盘后新实例重载仍退役"


def test_deprecate_is_idempotent() -> None:
    tracker = EffectTracker()
    lib = _library()

    lib.deprecate(_SID, effect_tracker=tracker)
    lib.deprecate(_SID, effect_tracker=tracker)

    assert lib.lookup(_SID).status == "deprecated"
    assert len(tracker.audit("skills.deprecate")) == 1, "已退役 → 不重复记效应"


def test_deprecate_unknown_id_raises_key_error() -> None:
    with pytest.raises(KeyError):
        _library().deprecate("skills.sop.unknown")


def test_deprecate_is_reversible() -> None:
    tracker = EffectTracker()
    lib = _library()

    lib.deprecate(_SID, effect_tracker=tracker)
    assert lib.lookup(_SID).status == "deprecated"

    report = tracker.rollback("skills.deprecate")

    assert report.undo_failed == []
    assert lib.lookup(_SID).status == "active", "回滚恢复退役前状态"


# ---- SkillIterator 连续退化自动退役 ----


def test_consecutive_degradations_retire_skill() -> None:
    lib = _library()
    feedback = _degrading_feedback()
    it = _iterator(lib, feedback, retire_after=_RETIRE)

    for _ in range(_RETIRE - 1):
        _degrade(lib, feedback, it)
        assert lib.lookup(_SID).status == "active", "未达阈不退役"
    _degrade(lib, feedback, it)

    assert lib.lookup(_SID).status == "deprecated", "连续退化达阈 → 自动退役"


def test_degradation_retirement_is_reversible() -> None:
    tracker = EffectTracker()
    lib = _library()
    feedback = _degrading_feedback()
    it = _iterator(lib, feedback, retire_after=_RETIRE, tracker=tracker)

    for _ in range(_RETIRE):
        _degrade(lib, feedback, it)
    assert lib.lookup(_SID).status == "deprecated"

    tracker.rollback("skills.deprecate")

    assert lib.lookup(_SID).status == "active", "退役可撤销"


def test_promotion_resets_degradation_counter() -> None:
    """**判别性**：退化 2 次 → 提升归零 → 再退化 2 次，仍 **active**（若未归零则 4 ≥ 3 已退役）。"""
    lib = _library()
    feedback = _degrading_feedback()
    it = _iterator(lib, feedback, retire_after=_RETIRE)

    _degrade(lib, feedback, it)
    _degrade(lib, feedback, it)
    _promote(lib, feedback, it)
    assert lib.lookup(_SID).status == "active"
    _degrade(lib, feedback, it)
    _degrade(lib, feedback, it)

    assert lib.lookup(_SID).status == "active", "提升使计数归零 ⇒ 重计后 2 次不足以退役"


def test_default_off_never_retires() -> None:
    """**零回归锚**：缺省关（`retire_after=None`）连续多次退化仍 `active`。"""
    lib = _library()
    feedback = _degrading_feedback()
    it = _iterator(lib, feedback, retire_after=None)

    for _ in range(_RETIRE + 2):
        _degrade(lib, feedback, it)

    assert lib.lookup(_SID).status == "active", "缺省关 ⇒ 退化不改变 status（逐字不变）"


def test_retired_skill_leaves_routing() -> None:
    lib = _library()
    router = SkillRouter(lib)

    assert [m.skill.skill_id for m in router.match(_TASK)] == [_SID], "退役前可路由"

    lib.deprecate(_SID)

    assert router.match(_TASK) == [], "退役 ⇒ 退出路由候选"


# ---- 粘性防复活（SOP 重抽） ----


def test_retired_sop_skill_is_not_resurrected_by_reextraction() -> None:
    lib = SkillLibrary()
    sid = _skill_id_for(_TASK)
    lib.register(_skill(sid, status="deprecated"))
    extractor = SopExtractor(lib, writer=lambda _p: "1. 新步骤一\n2. 新步骤二", threshold=1)

    published = extractor.observe(_TASK, ["step"], ok=True)

    assert published is None, "已退役 ⇒ 重抽不入库"
    assert lib.lookup(sid).status == "deprecated", "粘性：重抽不得复活为 active"


def test_reextraction_after_activate_publishes() -> None:
    """对照锚：显式 `activate` 后再重抽，守卫不再拦截（复活走显式面）。"""
    lib = SkillLibrary()
    sid = _skill_id_for(_TASK)
    lib.register(_skill(sid, status="deprecated"))
    lib.activate(sid)
    extractor = SopExtractor(lib, writer=lambda _p: "1. 新步骤一\n2. 新步骤二", threshold=1)

    published = extractor.observe(_TASK, ["step"], ok=True)

    assert published is not None, "显式激活后重抽可入库"


# ---- 配置面（ConfigSpec 单一真源） ----


def _write_config(tmp_path: Path, extra: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    return str(cfg)


def _manager(
    tmp_path: Path, extra: str = "", *, environ: dict[str, str] | None = None
) -> ConfigManager:
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, extra),
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
    )
    manager.load()
    return manager


def test_spec_declares_skill_retirement() -> None:
    spec = {spec.key: spec for spec in config_specs()}["skills.retirement"]

    assert (spec.cli_flag, spec.env_var, spec.default, spec.map_to) == (
        "--skills-retirement",
        "CORE_SKILLS_RETIREMENT",
        False,
        "skills.retirement",
    )


def test_config_default_is_off(tmp_path: Path) -> None:
    assert _manager(tmp_path).skill_retirement() is False


def test_config_yaml_enables(tmp_path: Path) -> None:
    manager = _manager(tmp_path, "skills:\n  retirement: true\n")

    assert manager.skill_retirement() is True


def test_config_env_overrides(tmp_path: Path) -> None:
    manager = _manager(tmp_path, "", environ={"CORE_SKILLS_RETIREMENT": "true"})

    assert manager.skill_retirement() is True


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _retire_after(runtime: object) -> int | None:
    iterator = cast(SkillIterator, runtime.skill_iterator)  # type: ignore[attr-defined]
    return iterator._retire_after  # noqa: SLF001 — 接线断言


def test_build_runtime_default_wires_retirement_off(tmp_path: Path, state_dir: Path) -> None:
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert _retire_after(runtime) is None


def test_build_runtime_wires_retirement_when_enabled(tmp_path: Path, state_dir: Path) -> None:
    runtime = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, "skills:\n  retirement: true\n"))
    )

    assert _retire_after(runtime) == RETIRE_AFTER_DEGRADATIONS
