"""交付流水线（ci-cd）：质量门禁四道。

顺序执行 lint/typecheck/test/build 四道门禁；任一阻断级门禁失败阻断交付
并抛 GATE_FAILED。门禁执行器可注入；生产**缺省**执行器以 stdlib ``subprocess`` 直跑
`GATE_COMMANDS` 基准命令（零第三方依赖）。

对应接口：doc/03-interfaces/ci-cd-interface.md §2
"""

from __future__ import annotations

import shlex
import subprocess
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path

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

# 结晶面（evolution）门禁**标记**：门名 → 选它的可读理由（**不复制命令字符串**）。
# 结晶面是「候选能否发布」的判据面，只取与之一一因果相关的两道：lint（轻量静态门，
# 语法/风格面回归，亚秒级）与 test（行为回归门）。typecheck（类型卫生）与 build（打包）
# 属**交付面**判据，与候选能否发布无因果关系且成本高，不入结晶面。
# 详见 doc/openspec/specs/evolution/spec.md「验证门」。
CRYSTALLIZATION_GATE_MARKS: dict[str, str] = {
    "lint": "轻量静态门：语法/风格面回归，亚秒级",
    "test": "行为回归门：仓库级测试套件",
}


def crystallization_gates() -> tuple[str, ...]:
    """派生结晶面门禁子集：**按标记从 `GATE_COMMANDS` 派生**（不另立第二份门禁清单）。

    顺序随**单一真源**（而非标记的书写顺序），命令字符串仍只有 `GATE_COMMANDS` 一份。
    标记命中真源里不存在的门名 ⇒ 抛 `GATE_FAILED`（fail-closed：标记与真源漂移必须炸出来，
    不得静默少跑一门）。
    """
    unknown = [kind for kind in CRYSTALLIZATION_GATE_MARKS if kind not in GATE_COMMANDS]
    if unknown:
        raise CiCdError(
            CiCdErrorCode.GATE_FAILED,
            f"结晶面门禁标记命中未注册的门名: {', '.join(sorted(unknown))}",
        )
    return tuple(kind for kind in GATE_COMMANDS if kind in CRYSTALLIZATION_GATE_MARKS)


# 单道门禁缺省超时：全量 pytest 亦留足余量，同时杜绝无限挂起。
_DEFAULT_TIMEOUT = 600.0

# 失败 reason 中保留的输出尾部上限：够定位问题，又不把整份测试输出塞进日志。
_MAX_REASON_CHARS = 2000


def _failure_reason(proc: subprocess.CompletedProcess[str]) -> str:
    """非零退出的原因：退出码 + **有界**输出尾部（本地工具诊断文本，无凭据面）。"""
    output = (proc.stdout + proc.stderr).strip()
    if not output:
        return f"退出码 {proc.returncode}"
    return f"退出码 {proc.returncode}：{output[-_MAX_REASON_CHARS:]}"


class SubprocessGateExecutor:
    """生产门禁执行器：stdlib ``subprocess`` 直跑 `GATE_COMMANDS`（零第三方依赖，不经 shell）。

    「跑不起来」（工具缺失 / 超时）与「跑失败」（非零退出）同样归一为**该门禁未通过**的结果载体，
    交 `CICDPipeline` 按既有「门禁失败阻断」路径处理 —— 执行器**不向调用方抛裸异常**。
    """

    def __init__(
        self,
        *,
        commands: Mapping[str, str] | None = None,
        cwd: str | Path | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.commands = dict(commands) if commands is not None else dict(GATE_COMMANDS)
        self._cwd = Path(cwd) if cwd is not None else None
        self._timeout = timeout

    def __call__(self, gate: Gate) -> GateResult:
        command = self.commands.get(gate.kind)
        if command is None:
            raise CiCdError(CiCdErrorCode.GATE_FAILED, f"未知门禁类型: {gate.kind}")
        argv = shlex.split(command)
        try:
            proc = subprocess.run(
                argv,
                cwd=str(self._cwd) if self._cwd is not None else None,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except FileNotFoundError:
            return GateResult(passed=False, reason=f"找不到可执行文件：{argv[0]}")
        except subprocess.TimeoutExpired:
            return GateResult(
                passed=False, reason=f"门禁 {gate.kind} 超过超时阈值 {self._timeout:g}s"
            )
        if proc.returncode == 0:
            return GateResult(passed=True)
        return GateResult(passed=False, reason=_failure_reason(proc))


def build_gate_executor(
    *,
    commands: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> SubprocessGateExecutor:
    """生产门禁执行器工厂：返回以 stdlib ``subprocess`` 直跑 `GATE_COMMANDS` 的执行器。"""
    return SubprocessGateExecutor(commands=commands, cwd=cwd, timeout=timeout)


class CICDPipeline:
    """质量门禁：顺序执行四道门禁，全通过才放行交付。"""

    def __init__(self, *, executor: Callable[[Gate], GateResult] | None = None) -> None:
        self._executor = executor if executor is not None else build_gate_executor()

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
