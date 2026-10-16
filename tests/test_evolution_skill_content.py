"""0236 · 技能候选内容生成（DI writer + 内容级验证 + 结晶映射）。"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import pytest

from core.configuration import ConfigManager
from core.evolution import (
    GATE_CALIBER,
    Diagnoser,
    DiagnosisReport,
    Evaluator,
    EvolutionEngine,
    EvolutionError,
    EvolutionErrorCode,
    GenerationCandidate,
    Proposer,
    Validator,
)
from core.evolution.content import (
    SkillContent,
    build_skill_content_prompt,
    skill_content_writer_with,
    validate_skill_content,
)
from core.runtime import build_runtime
from core.skills import SkillLibrary

_MAX_FAILURE_NOTES = 3
_MAX_NOTE_CHARS = 400

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _valid_content(**overrides: Any) -> SkillContent:
    base = {
        "task_types": ["retrieve"],
        "instructions": "先查记忆再回答",
        "param_schema": {"type": "object"},
        "preconditions": ["memory 可用"],
        "description": "检索失败补救",
    }
    base.update(overrides)
    return SkillContent(**base)


def _skill_diagnosis(*, issue: str = "检索失败") -> DiagnosisReport:
    return DiagnosisReport(
        target_plugin="memory.retrieve",
        issue=issue,
        failure_notes=["note-a", "note-b"],
    )


# ---- 2.1 content.py：validate 四态 + prompt 有界 ----


def test_validate_skill_content_four_states() -> None:
    assert validate_skill_content(_valid_content()) is True
    assert validate_skill_content(asdict(_valid_content())) is True
    assert validate_skill_content(_valid_content(task_types=[])) is False
    assert validate_skill_content(_valid_content(instructions="  ")) is False
    assert (
        validate_skill_content({"task_types": ["t"], "instructions": "x", "param_schema": []})
        is False
    )
    assert validate_skill_content(None) is False


def test_build_skill_content_prompt_bounds_notes() -> None:
    notes = [f"{'甲' * (_MAX_NOTE_CHARS + 50)}-{i}" for i in range(_MAX_FAILURE_NOTES + 2)]
    prompt = build_skill_content_prompt("检索失败", notes)
    assert "检索失败" in prompt
    assert notes[_MAX_FAILURE_NOTES] not in prompt
    for note in notes[:_MAX_FAILURE_NOTES]:
        assert note[:_MAX_NOTE_CHARS] in prompt
        assert note not in prompt  # 超长原文不得整段入 prompt


# ---- 2.2 writer 工厂 ----


def test_skill_content_writer_parses_valid_json() -> None:
    payload = asdict(_valid_content())
    writer = skill_content_writer_with(lambda _p: json.dumps(payload))
    result = writer("prompt")
    assert result is not None
    assert result.task_types == payload["task_types"]
    assert result.instructions == payload["instructions"]


@pytest.mark.parametrize(
    "llm",
    [
        lambda _p: "not-json",
        lambda _p: json.dumps({"task_types": [], "instructions": "x", "param_schema": {}}),
        lambda _p: (_ for _ in ()).throw(RuntimeError("boom")),
    ],
)
def test_skill_content_writer_returns_none_on_failure(llm: Any) -> None:
    writer = skill_content_writer_with(llm)
    assert writer("prompt") is None


# ---- 2.3 Proposer ----


def test_proposer_injects_content_for_skill() -> None:
    content = _valid_content()
    proposer = Proposer(writer=lambda _p: content)
    candidate = proposer.propose(_skill_diagnosis())
    assert candidate.kind == "skill"
    assert candidate.delta["issue"] == "检索失败"
    assert candidate.delta["content"] == asdict(content)


def test_proposer_omits_content_key_when_writer_none_or_missing() -> None:
    failing = Proposer(writer=lambda _p: None)
    assert failing.propose(_skill_diagnosis()).delta == {"issue": "检索失败"}
    bare = Proposer()
    assert bare.propose(_skill_diagnosis()).delta == {"issue": "检索失败"}


def test_proposer_plugin_never_gets_content() -> None:
    content = _valid_content()
    proposer = Proposer(kind="plugin", writer=lambda _p: content)
    candidate = proposer.propose(DiagnosisReport(target_plugin="loop.default", issue="循环失败"))
    assert candidate.kind == "plugin"
    assert "content" not in candidate.delta


# ---- 2.4 Validator ----


def test_validator_rejects_empty_shell_when_required() -> None:
    calls: list[str] = []
    validator = Validator(
        review=lambda _c: calls.append("review") or True,
        tests=lambda _c: calls.append("tests") or {"lint": True},
        require_skill_content=True,
    )
    report = validator.validate(
        GenerationCandidate(
            generation=1,
            target_plugin="memory.retrieve",
            delta={"issue": "检索失败"},
            kind="skill",
        )
    )
    assert report.passed is False
    assert "空壳" in report.review
    assert report.test_results == {}
    assert calls == []


def test_validator_runs_existing_path_with_content() -> None:
    calls: list[str] = []
    validator = Validator(
        review=lambda _c: calls.append("review") or True,
        tests=lambda _c: calls.append("tests") or {"lint": True, "test": True},
        require_skill_content=True,
    )
    report = validator.validate(
        GenerationCandidate(
            generation=1,
            target_plugin="memory.retrieve",
            delta={"issue": "检索失败", "content": asdict(_valid_content())},
            kind="skill",
        )
    )
    assert report.passed is True
    assert calls == ["review", "tests"]


def test_validator_plugin_and_default_unaffected() -> None:
    plugin = Validator(
        review=lambda _c: True,
        tests=lambda _c: {"lint": True},
        require_skill_content=True,
    ).validate(
        GenerationCandidate(
            generation=1,
            target_plugin="loop.default",
            delta={"issue": "x"},
            kind="plugin",
        )
    )
    assert plugin.passed is True

    default = Validator(
        review=lambda _c: True,
        tests=lambda _c: {"lint": True},
    ).validate(
        GenerationCandidate(
            generation=1,
            target_plugin="memory.retrieve",
            delta={"issue": "x"},
            kind="skill",
        )
    )
    assert default.passed is True


# ---- 2.5 结晶（直接测 _crystallize_skill 映射；公开 crystallize 另有门禁/评测守卫）----


def _skill_engine(library: SkillLibrary) -> EvolutionEngine:
    return EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=Proposer(),
        validator=Validator(review=lambda _c: True, tests=lambda _c: {"lint": True}),
        evaluator=Evaluator(),
        library=library,
    )


def test_crystallize_maps_content_fields_and_description_fallback() -> None:
    library = SkillLibrary()
    content = _valid_content(description="", instructions="用 sk-abcdefgh12 调用")
    candidate = GenerationCandidate(
        generation=1,
        target_plugin="memory.retrieve",
        delta={"issue": "检索失败", "content": asdict(content)},
        kind="skill",
    )
    outcome = _skill_engine(library)._crystallize_skill(candidate)  # noqa: SLF001
    assert outcome.status == "published"
    skill = library.lookup(outcome.skill_id or "")
    assert skill.task_types == content.task_types
    assert skill.preconditions == content.preconditions
    assert skill.param_schema == content.param_schema
    assert skill.description == "检索失败"  # description 空 ⇒ 回退 issue
    assert "sk-abcdefgh12" not in skill.instructions
    assert "<redacted>" in skill.instructions


def test_crystallize_empty_shell_fallback_unchanged() -> None:
    library = SkillLibrary()
    candidate = GenerationCandidate(
        generation=1,
        target_plugin="memory.retrieve",
        delta={"issue": "检索失败"},
        kind="skill",
    )
    outcome = _skill_engine(library)._crystallize_skill(candidate)  # noqa: SLF001
    skill = library.lookup(outcome.skill_id or "")
    assert skill.description == "检索失败"
    assert skill.instructions == ""
    assert skill.task_types == []


def test_crystallize_prefers_content_description() -> None:
    library = SkillLibrary()
    content = _valid_content(description="可读描述")
    candidate = GenerationCandidate(
        generation=1,
        target_plugin="memory.retrieve",
        delta={"issue": "检索失败", "content": asdict(content)},
        kind="skill",
    )
    _skill_engine(library)._crystallize_skill(candidate)  # noqa: SLF001
    assert library.lookup("skills.evolution.memory.retrieve").description == "可读描述"


# ---- 2.6 GATE_CALIBER ----


def test_gate_caliber_is_three() -> None:
    assert GATE_CALIBER == 3  # noqa: PLR2004 — 口径版本字面量即本 change 的契约


def test_caliber_2_confirmed_is_stale() -> None:
    library = SkillLibrary()
    engine = EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=Proposer(),
        validator=Validator(review=lambda _c: True, tests=lambda _c: {"lint": True}),
        evaluator=Evaluator(),
        library=library,
    )
    candidate = GenerationCandidate(
        generation=1,
        target_plugin="memory.retrieve",
        delta={"issue": "x", "content": asdict(_valid_content())},
        kind="skill",
        status="confirmed",
        caliber=2,
    )
    with pytest.raises(EvolutionError) as exc_info:
        engine.crystallize(candidate)
    assert exc_info.value.code is EvolutionErrorCode.GATE_CALIBER_STALE


def test_caliber_3_crystallizes() -> None:
    """现口径候选：口径校验不阻断（映射面经 _crystallize_skill 验证）。"""
    library = SkillLibrary()
    candidate = GenerationCandidate(
        generation=1,
        target_plugin="memory.retrieve",
        delta={"issue": "x", "content": asdict(_valid_content())},
        kind="skill",
        status="confirmed",
        caliber=GATE_CALIBER,
    )
    assert candidate.caliber == GATE_CALIBER == 3  # noqa: PLR2004 — 现口径字面量
    outcome = _skill_engine(library)._crystallize_skill(candidate)  # noqa: SLF001
    assert outcome.status == "published"


# ---- 2.7 runtime 同开同关 ----


class _Reply:
    content = "PASS"


class _StubProvider:
    def __init__(self, **_kw: Any) -> None: ...

    def completion(self, _request: Any) -> _Reply:
        return _Reply()


def _passing_gate_executor(**_kw: Any) -> Any:
    class _GateResult:
        passed = True
        reason = ""

    def _run(_gate: Any) -> _GateResult:
        return _GateResult()

    return _run


def test_runtime_wires_writer_and_require_together(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("core.runtime.StdlibLLMProvider", _StubProvider)
    monkeypatch.setattr("core.runtime.build_gate_executor", _passing_gate_executor)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION, encoding="utf-8")
    runtime = build_runtime(ConfigManager(yaml_path=str(cfg)))
    assert runtime.evolution is not None
    engine = runtime.evolution.engine
    assert engine._proposer._writer is not None  # noqa: SLF001
    assert engine._validator._require_skill_content is True  # noqa: SLF001
