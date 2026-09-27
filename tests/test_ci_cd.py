"""ci-cd 单元测试（对齐契约红线：门禁四道 / 制品发布回滚 / 三错误码兜底）。"""

from __future__ import annotations

import pytest

from core.ci_cd import (
    GATE_COMMANDS,
    ArtifactPublisher,
    CiCdError,
    CiCdErrorCode,
    CICDPipeline,
    Gate,
    GateResult,
    PipelineRun,
)


def _passed_run(commit_ref: str = "abc123") -> PipelineRun:
    return PipelineRun(
        run_id="run-1",
        commit_ref=commit_ref,
        gates=[Gate(gate_id=k, kind=k, blocking=True) for k in GATE_COMMANDS],
        status="passed",
    )


def test_gate_commands_four_kinds() -> None:
    assert set(GATE_COMMANDS) == {"lint", "typecheck", "test", "build"}
    assert GATE_COMMANDS["lint"].startswith("ruff")
    assert GATE_COMMANDS["typecheck"] == "pyright"
    assert GATE_COMMANDS["test"].startswith("pytest")
    assert GATE_COMMANDS["build"].startswith("uv build")


def test_run_all_gates_pass() -> None:
    run = CICDPipeline(executor=lambda _g: GateResult(passed=True)).run("abc123")
    assert run.status == "passed"
    assert [g.kind for g in run.gates] == ["lint", "typecheck", "test", "build"]


def test_run_blocking_gate_fails() -> None:
    def executor(gate: Gate) -> GateResult:
        if gate.kind == "typecheck":
            return GateResult(passed=False, reason="E501")
        return GateResult(passed=True)

    with pytest.raises(CiCdError) as exc_info:
        CICDPipeline(executor=executor).run("abc123")
    assert exc_info.value.code is CiCdErrorCode.GATE_FAILED


def test_gate_unknown_kind() -> None:
    with pytest.raises(CiCdError) as exc_info:
        CICDPipeline(executor=lambda _g: GateResult(passed=True)).gate("coverage")
    assert exc_info.value.code is CiCdErrorCode.GATE_FAILED


def test_publish_on_passed_run() -> None:
    published: list[str] = []
    publisher = ArtifactPublisher(channel=lambda a: published.append(a.version))
    artifact = publisher.publish(_passed_run())
    assert artifact.version == "v1.0.0"
    assert published == ["v1.0.0"]


def test_publish_blocked_run_rejected() -> None:
    run = _passed_run()
    run.status = "blocked"
    with pytest.raises(CiCdError) as exc_info:
        ArtifactPublisher(channel=lambda _a: None).publish(run)
    assert exc_info.value.code is CiCdErrorCode.GATE_FAILED


def test_rollback_missing_version() -> None:
    with pytest.raises(CiCdError) as exc_info:
        ArtifactPublisher(channel=lambda _a: None).rollback("v9.0.0")
    assert exc_info.value.code is CiCdErrorCode.ARTIFACT_NOT_FOUND


def test_publish_unreachable_channel() -> None:
    with pytest.raises(CiCdError) as exc_info:
        ArtifactPublisher().publish(_passed_run())
    assert exc_info.value.code is CiCdErrorCode.CHANNEL_UNREACHABLE
