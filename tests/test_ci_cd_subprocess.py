"""ci-cd 生产门禁执行器（stdlib subprocess）用例（change 0091 / Phase 20 C3）。

以 `sys.executable -c …` 注入命令，**真实**走 subprocess（不依赖 PATH 上是否装了 ruff/pyright）。
覆盖：通过 / 非零退出（reason 含输出尾部）/ 工具缺失 / 超时 / 未知门禁类型 / 缺省工厂表。
"""

from __future__ import annotations

import sys

import pytest

from core.ci_cd import (
    GATE_COMMANDS,
    CiCdError,
    CiCdErrorCode,
    CICDPipeline,
    Gate,
    SubprocessGateExecutor,
    build_gate_executor,
)


def _gate(kind: str) -> Gate:
    return Gate(gate_id=kind, kind=kind, blocking=True)


def _exit(code: int, *, stderr: str = "") -> str:
    """构造一条以 code 退出的命令（可选往 stderr 写文本）。"""
    script = f"import sys; sys.stderr.write({stderr!r}); sys.exit({code})"
    return f"{sys.executable} -c {script!r}"


def test_executor_passes_on_zero_exit() -> None:
    executor = build_gate_executor(commands={"lint": f"{sys.executable} -c 'print(1)'"})
    result = executor(_gate("lint"))
    assert result.passed is True


def test_executor_reports_failure_with_output_tail() -> None:
    executor = build_gate_executor(commands={"typecheck": _exit(3, stderr="E501 line too long")})
    result = executor(_gate("typecheck"))
    assert result.passed is False
    assert "3" in result.reason
    assert "E501 line too long" in result.reason


def test_executor_missing_tool_is_failure_not_exception() -> None:
    executor = build_gate_executor(commands={"lint": "core-agent-no-such-binary-xyz check"})
    result = executor(_gate("lint"))
    assert result.passed is False
    assert "core-agent-no-such-binary-xyz" in result.reason


def test_executor_timeout_is_failure() -> None:
    executor = build_gate_executor(
        commands={"test": f"{sys.executable} -c 'import time; time.sleep(30)'"}, timeout=0.2
    )
    result = executor(_gate("test"))
    assert result.passed is False
    assert "超时" in result.reason


def test_executor_unknown_kind_raises_gate_failed() -> None:
    executor = build_gate_executor(commands={"lint": f"{sys.executable} -c 'print(1)'"})
    with pytest.raises(CiCdError) as exc_info:
        executor(_gate("coverage"))
    assert exc_info.value.code is CiCdErrorCode.GATE_FAILED


def test_default_executor_uses_gate_commands() -> None:
    assert SubprocessGateExecutor().commands == GATE_COMMANDS


def test_pipeline_default_executor_is_subprocess_adapter() -> None:
    """change 0091：缺省执行器不再是「离线未接」错误，而是 stdlib subprocess 执行器。"""
    pipeline = CICDPipeline()
    assert isinstance(pipeline._executor, SubprocessGateExecutor)


def test_pipeline_runs_four_real_gates() -> None:
    """端到端：四道门禁命令**真实**经 subprocess 执行，全通过则放行。"""
    commands = {kind: f"{sys.executable} -c 'print(1)'" for kind in GATE_COMMANDS}
    pipeline = CICDPipeline(executor=build_gate_executor(commands=commands))
    run = pipeline.run("abc123")
    assert run.status == "passed"
    assert [g.kind for g in run.gates] == ["lint", "typecheck", "test", "build"]
