"""质量门禁工具面用例（change 0111 / phase-27 切片 S1）。

覆盖：工具定义契约（coeffect 诚实声明 / 不可逆 / schema 枚举）、按名触发与结构化
返回、确认门（不可逆 ⇒ 未批准**零调用**）、未知门禁 fail-closed（**不触达**执行器）、
真执行器 seam（真 subprocess 且不出网）。
"""

from __future__ import annotations

import sys

from core.ci_cd import Gate, GateResult, build_gate_executor
from core.ci_cd.pipeline import _DEFAULT_TIMEOUT  # noqa: PLC2701 — 执行器内部上界锚点
from core.plugin_registry import CoeffectResolver
from core.tools import ToolErrorCode, ToolProvider
from core.tools.builtin import gate_run

_GATES = ("lint", "typecheck", "test", "build")


class _Runner:
    """记录调用的假门禁执行器（结构上与 `GateResult` 返回面一致）。"""

    def __init__(self, *, passed: bool = True, reason: str = "") -> None:
        self.calls: list[str] = []
        self._result = GateResult(passed=passed, reason=reason)

    def __call__(self, gate: str) -> GateResult:
        self.calls.append(gate)
        return self._result


def _provider() -> ToolProvider:
    resolver = CoeffectResolver()
    resolver.register("filesystem:write", True)
    resolver.register("process:spawn", True)
    return ToolProvider(coeffect_resolver=resolver)


def test_gate_run_definition_is_honest() -> None:
    tool = gate_run(gates=_GATES, run_gate=_Runner())
    definition = tool.definition
    assert definition.tool_id == "tools.gate_run"
    # 诚实声明：跑门禁＝spawn 子进程 + 写缓存目录 ⇒ 写类 coeffect 且不可逆
    assert definition.coeffects == ["process:spawn", "filesystem:write"]
    assert definition.reversible is False
    assert definition.schema["required"] == ["gate"]
    assert definition.schema["properties"]["gate"]["enum"] == list(_GATES)
    # 内部 600s 上界之外还有余量，避免工具层先于执行器超时
    assert definition.timeout_s > _DEFAULT_TIMEOUT


def test_gate_run_returns_structured_result() -> None:
    runner = _Runner()
    provider = _provider()
    provider.register(gate_run(gates=_GATES, run_gate=runner))
    result = provider.invoke("tools.gate_run", {"gate": "lint"}, trace_id="t", approved=True)
    assert result.ok is True
    assert result.data == {"gate": "lint", "passed": True, "reason": ""}
    assert runner.calls == ["lint"]


def test_gate_run_reports_failure_reason() -> None:
    runner = _Runner(passed=False, reason="3 failed")
    provider = _provider()
    provider.register(gate_run(gates=_GATES, run_gate=runner))
    result = provider.invoke("tools.gate_run", {"gate": "test"}, trace_id="t", approved=True)
    assert result.ok is True
    assert result.data["passed"] is False
    assert "3 failed" in result.data["reason"]


def test_gate_run_irreversible_requires_approval() -> None:
    runner = _Runner()
    provider = _provider()
    provider.register(gate_run(gates=_GATES, run_gate=runner))
    result = provider.invoke("tools.gate_run", {"gate": "lint"}, trace_id="t")
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ToolErrorCode.IRREVERSIBLE_BLOCKED
    assert runner.calls == []  # fail-closed：未批准不触达执行器


def test_gate_run_unknown_gate_fail_closed() -> None:
    runner = _Runner()
    provider = _provider()
    provider.register(gate_run(gates=_GATES, run_gate=runner))
    result = provider.invoke("tools.gate_run", {"gate": "deploy"}, trace_id="t", approved=True)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ToolErrorCode.EXECUTION_FAILED
    assert runner.calls == []  # 白名单外不触达执行器（Validator 不校验 enum 的兜底）


def _real_runner(commands: dict[str, str]):
    """把既有生产执行器适配为「门禁名 → 结果」注入面（与组合根同一适配形状）。"""
    executor = build_gate_executor(commands=commands)

    def run_gate(kind: str) -> GateResult:
        return executor(Gate(gate_id=f"gate.{kind}", kind=kind))

    return run_gate


def test_gate_run_with_real_executor_passes() -> None:
    runner = _real_runner({"probe": f"{sys.executable} -c 'print(1)'"})
    provider = _provider()
    provider.register(gate_run(gates=("probe",), run_gate=runner))
    result = provider.invoke("tools.gate_run", {"gate": "probe"}, trace_id="t", approved=True)
    assert result.ok is True
    assert result.data["passed"] is True


def test_gate_run_with_real_executor_reports_nonzero_exit() -> None:
    script = "import sys; sys.stderr.write('E501 line too long'); sys.exit(3)"
    runner = _real_runner({"probe": f"{sys.executable} -c {script!r}"})
    provider = _provider()
    provider.register(gate_run(gates=("probe",), run_gate=runner))
    result = provider.invoke("tools.gate_run", {"gate": "probe"}, trace_id="t", approved=True)
    assert result.ok is True
    assert result.data["passed"] is False
    assert "E501 line too long" in result.data["reason"]
