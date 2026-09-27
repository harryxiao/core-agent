"""交付流水线（ci-cd）：质量门禁四道。

顺序执行 lint/typecheck/test/build 四道门禁；任一阻断级门禁失败阻断交付
并抛 GATE_FAILED。门禁执行器可注入（默认引用 development-toolchain，离线未接）。

对应接口：doc/03-interfaces/ci-cd-interface.md §2
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from .errors import CiCdError, CiCdErrorCode
from .models import Gate, GateResult, PipelineRun

# 门禁顺序（lint → typecheck → test → build），与 development-toolchain 基线一致。
_GATE_KINDS = ("lint", "typecheck", "test", "build")

# 四道门禁命令映射：复用 Phase -1 固化的门禁基线，不另起一套。
GATE_COMMANDS: dict[str, str] = {
    "lint": "ruff check src tests",
    "typecheck": "pyright",
    "test": "pytest -q",
    "build": "uv build",
}


def build_gate_executor(gate: Gate) -> GateResult:
    """生产门禁执行器：引用 development-toolchain（ruff/pyright/pytest/uv build），离线未接。"""
    raise CiCdError(
        CiCdErrorCode.GATE_FAILED,
        f"门禁 {gate.kind} 需接 development-toolchain 执行器（离线未接）",
    )


class CICDPipeline:
    """质量门禁：顺序执行四道门禁，全通过才放行交付。"""

    def __init__(self, *, executor: Callable[[Gate], GateResult] | None = None) -> None:
        self._executor = executor if executor is not None else build_gate_executor

    def gate(self, kind: str) -> Gate:
        """取回指定门禁；门禁实现引用 development-toolchain。"""
        if kind not in _GATE_KINDS:
            raise CiCdError(CiCdErrorCode.GATE_FAILED, f"未知门禁类型: {kind}")
        return Gate(gate_id=kind, kind=kind, blocking=True)

    def run(self, commit_ref: str) -> PipelineRun:
        """顺序执行四道门禁；任一阻断级门禁失败阻断交付，抛 GATE_FAILED。"""
        run_id = uuid.uuid4().hex
        gates = [self.gate(kind) for kind in _GATE_KINDS]
        for gate in gates:
            result = self._executor(gate)
            if gate.blocking and not result.passed:
                raise CiCdError(
                    CiCdErrorCode.GATE_FAILED, f"门禁 {gate.kind} 失败: {result.reason}"
                )
        return PipelineRun(run_id=run_id, commit_ref=commit_ref, gates=gates, status="passed")
