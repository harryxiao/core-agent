"""原生实施执行器（evolution）：把架构级候选的 `accepted` 结局推进为 `implemented`。

**可选能力**（`features.evolution_executor`，缺省关）且**只由操作面显式驱动**
（`core-agent evolve implement`）：不挂 loop 的热/冷路径节拍、不注册为任何 Agent 可调用的工具。
自改代码不经模型手，也不在智能体一轮收尾处同步跑四道门禁（单门超时上界 600s ⇒ 那是阻塞热路径）。

两阶段，**复核前 SHALL NOT 落地**：

1. **筹备**（`--dry-run`）：补丁生产者产出单文件补丁 → 范围守卫 → 应用 → 跑**冻结验证门** →
   **回退**。制品（补丁内容 + 被改文件的原内容 + 各门结论）挂到**既有候选台账**同一条记录上
   （不建第二个持久化库：CLI 是一次性进程，制品不落盘则「待复核」只活在一次进程里）。
2. **落地**：人工复核关（与候选目标一致、`op` 可区分的**已批准**审批单）+ 漂移校验之后，应用
   **被复核的那一份**制品（不重新产出补丁），记可逆效应，候选状态与结局置 `implemented`。
   落地**只认门禁全过**（`gated=True`）的制品：筹备中断留下的 `gated=False` 残留不构成可复核对象
   （E69／change 0127）—— 否则从未跑过门禁的补丁会被永久应用。

两条独立判据协同守卫「改哪儿」：①**范围守卫**（`_scope_violation`，形状/白名单减信任集）；
②**路径与归因一致**（路径须由候选 `target_plugin` 经约定解析得出且文件确实存在）。守卫只查
形状是不够的 —— 模型完全可能给出一个「形状合法但改的是别人家」的路径。

对应规格：evolution/spec.md「架构级候选的原生实施（可选）」；裁决与已知局限见 ADR-0105。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from core.permission import is_approved
from core.plugin_registry import Effect, EffectTracker

from .author import PatchAuthor
from .errors import EvolutionError, EvolutionErrorCode
from .models import (
    EvolutionOutcome,
    GenerationCandidate,
    ImplementationRecord,
    PatchProposal,
)
from .pending import PendingQueue
from .plugin_ids import CORE_ROOT, INTERNAL_PLUGIN_IDS, module_path

#: 筹备与落地各自的效应 trace（效应按 trace 分组回滚；两者分开，回滚筹备不掀翻已落地的）。
PREPARE_TRACE = "evolution.prepare"
COMMIT_TRACE = "evolution.commit"

#: 实施复核单的操作标识（与 `confirm` 的 `evolution.publish` **可区分**：不得跨阶段复用）
IMPLEMENT_OP = "evolution.implement"

#: 允许修改的源码面（白名单形态：先定「允许什么」，再从中减信任集 —— 新增顶层目录自动落在
#: 允许面**之外**，不会因为「忘了加黑名单」而放行）。
_ALLOWED_ROOT = f"{CORE_ROOT}/"

#: 信任集（验证装置与信任链）：改它即改判据本身 —— 门禁命令单一真源、审批关、开关判据、
#: 进化引擎与台账（执行器自己的调用方与判据）、组合根与操作面、台账 IO。
_TRUST_PREFIXES = (
    f"{CORE_ROOT}/ci_cd/",
    f"{CORE_ROOT}/permission/",
    f"{CORE_ROOT}/evolution/",
    f"{CORE_ROOT}/configuration/",
)
_TRUST_FILES = (
    f"{CORE_ROOT}/runtime.py",
    f"{CORE_ROOT}/entry.py",
    f"{CORE_ROOT}/persistence.py",
)


class GateOutcome(Protocol):
    """门禁结果的最小结构面（消费侧声明）：只要求 ``passed`` / ``reason``。

    交付流水线的 ``GateResult`` 与之结构兼容 —— 本层因此无须依赖 ci-cd 层，执行器由组合根注入。
    """

    passed: bool
    reason: str


def _scope_violation(path: str) -> str | None:
    """范围守卫：补丁路径越界则返回原因（人类可读），放行返回 ``None``。"""
    if path.startswith("/") or "\\" in path or "\0" in path:
        return "补丁路径须是仓内相对路径（POSIX 形态）"
    parts = path.split("/")
    if "." in parts or ".." in parts:
        return "补丁路径不得含 `.` / `..` 段"
    if not path.startswith(_ALLOWED_ROOT):
        return f"补丁只允许落在 {_ALLOWED_ROOT}*（源码面）"
    if not path.endswith(".py"):
        return "补丁只允许落在 Python 源码"
    if path.startswith(_TRUST_PREFIXES) or path in _TRUST_FILES:
        return "目标属验证装置或信任链（改它即改判据本身）"
    return None


def source_reader(root: str | Path) -> Callable[[str], str | None]:
    """按仓根读源码（仓内相对路径）；不存在 / 不可读 ⇒ ``None``（可行性由守卫判，读侧不抛）。"""
    base = Path(root)

    def _read(path: str) -> str | None:
        try:
            return (base / path).read_text(encoding="utf-8")
        except OSError:
            return None

    return _read


class EvolutionExecutor:
    """架构级候选的原生实施执行器（两阶段；门禁冻结、路径受守卫与归因双重约束）。"""

    def __init__(  # noqa: PLR0913 — 注入面为 6 项，皆为可选依赖注入
        self,
        *,
        author: PatchAuthor,
        run_gate: Callable[[str], GateOutcome],
        gates: tuple[str, ...],
        effects: EffectTracker,
        queue: PendingQueue,
        root: str | Path,
    ) -> None:
        self.author = author
        self.run_gate = run_gate
        # 门禁名单**外部给定**（组合根取自 `GATE_COMMANDS` 单一真源）：执行器不自选门禁
        self.gates = tuple(gates)
        self.effects = effects
        self.queue = queue
        self.root = Path(root)

    # ---- 阶段一：筹备 ----

    def prepare(self, candidate: GenerationCandidate) -> ImplementationRecord:
        """筹备：补丁 → 守卫 → 应用 → 跑冻结门 → **回退**；制品落台账待复核，工作树不留改动。"""
        path = self._admit(candidate)
        target = self.root / path
        if not target.is_file():
            raise EvolutionError(
                EvolutionErrorCode.IMPLEMENT_REJECTED,
                f"归因目标模块不存在（{path}）—— 不凭约定凭空造文件",
            )
        current = target.read_text(encoding="utf-8")
        self._reject_drifted_worktree(candidate.candidate_id, current, path)

        proposal = self.author(candidate)
        if proposal.path != path:
            raise EvolutionError(
                EvolutionErrorCode.IMPLEMENT_REJECTED,
                f"补丁路径与候选归因不符（{proposal.path} != {path}）",
            )
        record = ImplementationRecord(
            candidate_id=candidate.candidate_id, path=path, before=current, content=proposal.content
        )
        if not self.queue.attach_implementation(record):
            raise EvolutionError(
                EvolutionErrorCode.IMPLEMENT_REJECTED,
                f"候选不在台账（{candidate.candidate_id}）—— 制品无处承载",
            )

        gate, failed = self._run_gates(record, path)
        if failed is not None:
            self.queue.clear_implementation(candidate.candidate_id)
            raise EvolutionError(
                EvolutionErrorCode.GATE_REJECTED,
                f"实施筹备未过冻结验证门：{failed}（{path}）",
            )
        staged = ImplementationRecord(
            candidate_id=record.candidate_id,
            path=record.path,
            before=record.before,
            content=record.content,
            gate=gate,
            gated=True,
        )
        self.queue.attach_implementation(staged)
        return staged

    # ---- 阶段二：落地 ----

    def commit(
        self, candidate: GenerationCandidate, *, approval: Any | None = None
    ) -> EvolutionOutcome:
        """落地：复核关 + 漂移校验通过后，应用**被复核的那一份**制品并记可逆效应。"""
        self._admit(candidate)
        record = self.staged(candidate.candidate_id)
        if record is None:
            raise EvolutionError(
                EvolutionErrorCode.IMPLEMENT_REJECTED,
                f"该候选没有待复核制品（{candidate.candidate_id}）"
                f"—— 先 `evolve implement {candidate.candidate_id} --dry-run`",
            )
        self._require_implement_ticket(approval, candidate.target_plugin)
        target = self.root / record.path
        if target.read_text(encoding="utf-8") != record.before:
            raise EvolutionError(
                EvolutionErrorCode.IMPLEMENT_STALE,
                f"目标文件自筹备以来已被改动（{record.path}）—— 拒绝覆盖，请重新筹备",
            )
        self._apply(record.path, record.content, candidate.candidate_id, trace=COMMIT_TRACE)
        self.queue.attach_implementation(
            ImplementationRecord(
                candidate_id=record.candidate_id,
                path=record.path,
                before=record.before,
                content=record.content,
                gate=record.gate,
                gated=True,
                committed=True,
            )
        )
        candidate.status = "implemented"
        self.queue.flush()
        return EvolutionOutcome(status="implemented", candidate=candidate)

    # ---- 查询 ----

    def staged(self, candidate_id: str) -> ImplementationRecord | None:
        """该候选的**待复核**制品（未筹备 / **未过门** / 已落地 ⇒ ``None``）。

        「待复核」≡ **门禁全过**（`gated=True`）且尚未落地：筹备中断（门禁抛错 / 进程被杀）留下的
        `gated=False` 残留制品**不是**可复核对象（E69／change 0127），否则从未跑过门禁的补丁会被
        放行落地。
        """
        record = self.queue.implementation_of(candidate_id)
        return record if record is not None and record.gated and not record.committed else None

    def staged_all(self) -> list[ImplementationRecord]:
        """全部待复核制品（操作面 `evolve pending` 的呈现源）。"""
        return self.queue.staged()

    # ---- 内部 ----

    def _admit(self, candidate: GenerationCandidate) -> str:
        """前置与范围守卫：返回归因约定的目标路径；任一不满足即 fail-closed。"""
        if candidate.kind != "plugin" or candidate.status != "confirmed":
            raise EvolutionError(
                EvolutionErrorCode.IMPLEMENT_REJECTED,
                f"原生实施只适用于**已人工确认**的架构级候选"
                f"（kind={candidate.kind}, status={candidate.status}）",
            )
        if candidate.target_plugin not in INTERNAL_PLUGIN_IDS:
            raise EvolutionError(
                EvolutionErrorCode.IMPLEMENT_REJECTED,
                f"归因目标不在内部核心模块白名单内（{candidate.target_plugin}）",
            )
        path = module_path(candidate.target_plugin)
        violation = _scope_violation(path)
        if violation is not None:
            raise EvolutionError(
                EvolutionErrorCode.IMPLEMENT_REJECTED, f"范围守卫拒绝（{path}）：{violation}"
            )
        return path

    def _reject_drifted_worktree(self, candidate_id: str, current: str, path: str) -> None:
        """上次筹备若未回退（工作树与记录的原内容不符）⇒ 拒绝，不把脏内容当成「原内容」。"""
        existing = self.queue.implementation_of(candidate_id)
        if existing is None:
            return
        if existing.before != current:
            raise EvolutionError(
                EvolutionErrorCode.IMPLEMENT_STALE,
                f"工作树与上次筹备记录的原内容不符（{path}）—— 拒绝据此重算原内容",
            )
        self.queue.clear_implementation(candidate_id)  # 重新筹备：旧制品作废，从头再来

    def _run_gates(
        self, record: ImplementationRecord, path: str
    ) -> tuple[dict[str, dict[str, Any]], str | None]:
        """应用补丁 → 顺序跑冻结门 → **无论成败都回退**工作树；返回（各门结论, 首个失败门）。"""
        self._apply(path, record.content, record.candidate_id, trace=PREPARE_TRACE)
        gate: dict[str, dict[str, Any]] = {}
        failed: str | None = None
        try:
            for kind in self.gates:
                outcome = self.run_gate(kind)
                gate[kind] = {"passed": bool(outcome.passed), "reason": outcome.reason}
                if not outcome.passed:
                    failed = f"{kind}（{outcome.reason}）"
                    break
        finally:
            report = self.effects.rollback(f"{PREPARE_TRACE}.{record.candidate_id}")
        if report.undo_failed:
            raise EvolutionError(
                EvolutionErrorCode.IMPLEMENT_REJECTED,
                f"筹备回退失败（{path}）—— 工作树可能残留补丁，须人工核对",
            )
        return gate, failed

    def _apply(self, path: str, content: str, candidate_id: str, *, trace: str) -> None:
        """写入并登记可逆效应（undo 恢复写入前的原内容）。"""
        target = self.root / path
        before = target.read_text(encoding="utf-8")

        def undo() -> None:
            target.write_text(before, encoding="utf-8")

        self.effects.record(
            Effect(
                op="evolution.implement",
                target=path,
                undo=undo,
                reversible=True,
                coeffect=[],
                trace_id=f"{trace}.{candidate_id}",
                ts=time.time(),
            )
        )
        target.write_text(content, encoding="utf-8")

    @staticmethod
    def _require_implement_ticket(approval: Any | None, target_plugin: str) -> None:
        """复核关 fail-closed：须一张目标一致、`op` 可区分的**已批准**审批单。"""
        if approval is None or not is_approved(approval):
            raise EvolutionError(
                EvolutionErrorCode.CONFIRM_REQUIRED,
                f"实施未经人工复核（{target_plugin}）",
            )
        if getattr(approval.request, "op", "") != IMPLEMENT_OP:
            raise EvolutionError(
                EvolutionErrorCode.CONFIRM_REQUIRED,
                f"审批单非实施复核单（op={getattr(approval.request, 'op', '')}）—— 不得跨阶段复用",
            )
        if approval.request.target != target_plugin:
            raise EvolutionError(
                EvolutionErrorCode.CONFIRM_REQUIRED,
                f"复核单目标与候选不符（{approval.request.target} != {target_plugin}）",
            )


__all__ = [
    "COMMIT_TRACE",
    "IMPLEMENT_OP",
    "PREPARE_TRACE",
    "EvolutionExecutor",
    "GateOutcome",
    "PatchProposal",
    "source_reader",
]
