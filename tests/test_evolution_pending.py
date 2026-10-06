"""进化人工确认队列的持久化与操作面（change 0055 / 账本 A4）。

证明两件事：① 待确认候选**跨进程**可用（稳定身份 + 门禁/评测随候选落盘 → 重启后
`confirm` → `crystallize` 仍能发布）；② 生产侧**有**调用方（CLI `evolve pending|confirm|reject`
把待确认队列驱动起来，high 风险候选由操作面签发审批单）。
"""

from __future__ import annotations

import json

import pytest

from core.configuration import ConfigManager
from core.entry import main
from core.evolution import (
    BenchmarkRegistry,
    Diagnoser,
    Evaluator,
    EvolutionEngine,
    EvolutionError,
    EvolutionErrorCode,
    GenerationCandidate,
    PendingQueue,
    Proposer,
    Trace,
    Validator,
)
from core.permission import ApprovalRequest, ApprovalWorkflow
from core.runtime import _skill_state_path, build_runtime
from core.skills import SkillLibrary


def _trace(trace_id: str, *, success: bool, plugin_id: str | None = None) -> Trace:
    return Trace(
        trace_id=trace_id,
        task_type="t",
        action={"a": 1},
        result="ok",
        success=success,
        plugin_id=plugin_id,
    )


class _RegisteredBaselines(BenchmarkRegistry):
    """测试替身：数据面上任意目标都视为已注册基线 0.5（判定面仍是真 `Evaluator`）。"""

    def baseline_of(self, _plugin_id: str) -> float | None:
        return 0.5


def _passing_evaluator() -> Evaluator:
    """过门评测器：基线可比（0.5）+ 留出分 0.9 ⇒ 真实地判 publish（0119 起无参裸桩不再恒通过）。"""
    return Evaluator(registry=_RegisteredBaselines(), score_fn=lambda _c: 0.9)


def _passing_validator() -> Validator:
    """过门验证门：review 与运行时测试都判过（0120 起无参 `Validator()` 不再恒通过 = 不得放行）。"""
    return Validator(review=lambda _c: True, tests=lambda _c: {"lint": True, "test": True})


def _engine(**kw: object) -> EvolutionEngine:
    return EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=kw.get("proposer", Proposer()),  # type: ignore[arg-type]
        validator=_passing_validator(),
        evaluator=_passing_evaluator(),
        library=kw.get("library"),  # type: ignore[arg-type]
        pending=kw.get("pending"),  # type: ignore[arg-type]
    )


def _pending(engine: EvolutionEngine) -> GenerationCandidate:
    """跑一次闭环得到过门候选（status="pending"）。"""
    outcome = engine.run_cycle([_trace("1", success=False, plugin_id="memory.retrieve")])
    assert outcome.status == "pending" and outcome.candidate is not None
    return outcome.candidate


# ---- 稳定身份 ----


def test_candidate_id_is_unique_across_instances() -> None:
    """同样 generation/target 的两个候选身份不同（进程内自增的 generation 不可作键）。"""
    a = GenerationCandidate(generation=1, target_plugin="p", delta={}, kind="skill")
    b = GenerationCandidate(generation=1, target_plugin="p", delta={}, kind="skill")
    assert a.candidate_id != b.candidate_id
    assert a.candidate_id == a.candidate_id  # 构造即固化


# ---- 队列落盘与恢复 ----


def test_pending_queue_round_trips(tmp_path) -> None:
    path = tmp_path / "pending.json"
    engine = _engine(pending=PendingQueue(path=path))
    candidate = _pending(engine)
    assert path.exists()
    assert [c.candidate_id for c in engine.pending()] == [candidate.candidate_id]

    restored = PendingQueue(path=path)
    items = restored.records()
    assert len(items) == 1
    assert items[0].candidate.candidate_id == candidate.candidate_id
    assert items[0].candidate.target_plugin == "memory.retrieve"
    assert items[0].gate is not None and items[0].gate.passed is True
    assert items[0].eval is not None and items[0].eval.verdict == "publish"


def test_pending_queue_without_path_is_memory_only(tmp_path) -> None:
    engine = _engine(pending=PendingQueue())
    _pending(engine)
    assert list(tmp_path.iterdir()) == []


def test_pending_queue_corrupt_file_degrades_to_empty(tmp_path) -> None:
    path = tmp_path / "pending.json"
    path.write_text("{ not json", encoding="utf-8")
    assert PendingQueue(path=path).records() == []


def test_pending_queue_tolerates_partial_record(tmp_path) -> None:
    """记录缺门禁/评测时仍可恢复候选（半状态不抛）。"""
    path = tmp_path / "pending.json"
    path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "candidate_id": "abc",
                        "generation": 1,
                        "target_plugin": "p",
                        "delta": {},
                        "kind": "skill",
                        "status": "pending",
                        "risk_level": "low",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    items = PendingQueue(path=path).records()
    assert items[0].candidate.candidate_id == "abc"
    assert items[0].gate is None and items[0].eval is None


# ---- 跨进程语义（回归：检索键不得用 id(obj)） ----


def test_pending_survives_restart_and_publishes(tmp_path) -> None:
    """同路径新引擎：恢复候选后 confirm → crystallize 得 published。"""
    path = tmp_path / "pending.json"
    library = SkillLibrary()
    first = _engine(pending=PendingQueue(path=path), library=library)
    candidate_id = _pending(first).candidate_id

    second = _engine(pending=PendingQueue(path=path), library=library)
    restored = second.find(candidate_id)
    assert restored is not None
    second.confirm(restored)
    assert second.crystallize(restored).status == "published"
    assert library.lookup("skills.evolution.memory.retrieve") is not None


def test_high_risk_candidate_survives_restart(tmp_path) -> None:
    path = tmp_path / "pending.json"
    first = _engine(pending=PendingQueue(path=path), proposer=Proposer(kind="plugin"))
    candidate_id = _pending(first).candidate_id

    second = _engine(pending=PendingQueue(path=path), proposer=Proposer(kind="plugin"))
    restored = second.find(candidate_id)
    assert restored is not None and restored.risk_level == "high"
    workflow = ApprovalWorkflow()
    ticket = workflow.create(
        ApprovalRequest(
            op="evolution.publish",
            target="memory.retrieve",
            impact_summary="x",
            rollback_plan="dissolve",
            trace_id="evolution",
        )
    )
    workflow.approve(ticket)
    second.confirm(restored, approval=ticket)
    assert second.crystallize(restored).status == "accepted"


# ---- 队列语义：确认/拒绝即出队 ----


def test_pending_snapshot_excludes_resolved(tmp_path) -> None:
    engine = _engine(pending=PendingQueue(path=tmp_path / "pending.json"))
    candidate = _pending(engine)
    engine.confirm(candidate)
    assert engine.pending() == []
    assert engine.find(candidate.candidate_id) is not None  # 仍留痕，只是不在待确认快照


def test_reject_marks_and_blocks_publish(tmp_path) -> None:
    engine = _engine(pending=PendingQueue(path=tmp_path / "pending.json"), library=SkillLibrary())
    candidate = _pending(engine)
    engine.reject(candidate, reason="证据太弱")
    assert candidate.status == "rejected"
    assert engine.pending() == []
    with pytest.raises(EvolutionError) as exc_info:
        engine.crystallize(candidate)
    assert exc_info.value.code is EvolutionErrorCode.CANDIDATE_PENDING


def test_reject_round_trips(tmp_path) -> None:
    path = tmp_path / "pending.json"
    engine = _engine(pending=PendingQueue(path=path))
    candidate = _pending(engine)
    engine.reject(candidate)
    assert PendingQueue(path=path).records()[0].candidate.status == "rejected"


def test_find_missing_returns_none() -> None:
    assert _engine(pending=PendingQueue()).find("nope") is None


# ---- 操作面（CLI） ----


def _write_config(tmp_path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n",
        encoding="utf-8",
    )
    return str(cfg)


def _seed(*, kind: str = "skill") -> str:
    """把一条待确认候选写进组合根会读的落盘路径，返回其 id。"""
    proposer_kind = "plugin" if kind == "plugin" else "skill"
    engine = EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=Proposer(kind=proposer_kind),  # type: ignore[arg-type]
        validator=_passing_validator(),
        evaluator=_passing_evaluator(),
        pending=PendingQueue(path=_skill_state_path("evolution-pending.json")),
    )
    return _pending(engine).candidate_id


@pytest.fixture
def cli_env(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return _write_config(tmp_path)


def test_evolve_pending_lists(cli_env, capsys: pytest.CaptureFixture[str]) -> None:
    candidate_id = _seed()
    assert main(["--config", cli_env, "evolve", "pending"]) == 0
    out = capsys.readouterr().out
    assert candidate_id in out
    assert "memory.retrieve" in out


def test_evolve_confirm_publishes(cli_env, capsys: pytest.CaptureFixture[str]) -> None:
    candidate_id = _seed()
    assert main(["--config", cli_env, "evolve", "confirm", candidate_id]) == 0
    assert "published" in capsys.readouterr().out
    assert main(["--config", cli_env, "evolve", "pending"]) == 0
    assert "待确认队列为空" in capsys.readouterr().out


def test_evolve_confirm_high_risk_signs_ticket(cli_env, capsys: pytest.CaptureFixture[str]) -> None:
    candidate_id = _seed(kind="plugin")
    assert main(["--config", cli_env, "evolve", "confirm", candidate_id]) == 0
    # 架构级候选批准后无产物落地 ⇒ CLI 不得说「已发布」
    out = capsys.readouterr().out
    assert "待人工实施" in out
    assert "published" not in out


def test_evolve_reject(cli_env, capsys: pytest.CaptureFixture[str]) -> None:
    candidate_id = _seed()
    assert main(["--config", cli_env, "evolve", "reject", candidate_id, "--note", "太弱"]) == 0
    assert "已拒绝" in capsys.readouterr().out


def test_evolve_confirm_unknown_id_fails(cli_env, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--config", cli_env, "evolve", "confirm", "nope"]) == 1
    assert "不在待确认队列" in capsys.readouterr().err


def test_evolve_reject_unknown_id_fails(cli_env, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--config", cli_env, "evolve", "reject", "nope"]) == 1
    assert "不在待确认队列" in capsys.readouterr().err


# ---- 生产装配 ----


def test_build_runtime_injects_pending_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    engine = runtime.evolution.engine
    assert isinstance(engine._pending, PendingQueue)  # noqa: SLF001 — 接线断言
    assert engine._pending._path is not None  # noqa: SLF001 — 已注入路径
