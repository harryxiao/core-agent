"""进化引擎（evolution）—— 四阶段结晶闭环编排。

`EvolutionEngine` 是进化层唯一满足 `Plugin` 契约的实体：编排
诊断 → 提案 → 验证门 → 留出评测，过门候选进人工确认队列，`confirm()` +
`crystallize()` 落库发布，退化时 `dissolve()` 溶解回退。`EvolutionTrigger`
按累计轮次 / 强制触发进化，后台低优先级执行。

对应接口：doc/03-interfaces/evolution-interface.md ｜ 规格 evolution/spec.md
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from typing import Any

from core.memory import Crystallizer, MemoryBackend, MemoryEntry
from core.permission import ApprovalTicket, is_approved
from core.skills import Skill, SkillLibrary

from .collector import Collector
from .curriculum import EvolutionGoal
from .diagnoser import Diagnoser
from .errors import EvolutionError, EvolutionErrorCode
from .evaluator import Evaluator
from .models import (
    GATE_CALIBER,
    DiagnosisReport,
    EvolutionOutcome,
    GenerationCandidate,
    Trace,
    TraceRef,
)
from .observation import ObservationRegistry
from .pending import PendingQueue
from .proposer import Proposer
from .validator import Validator


class EvolutionEngine:
    """进化引擎：四阶段闭环 + 人工确认队列 + 结晶/溶解。"""

    plugin_id = "evolution.engine"
    generation = 1
    schema: dict[str, Any] = {"type": "object"}
    coeffects: list[str] = []

    def __init__(  # noqa: PLR0913 — 四阶段组件与外部依赖均为构造注入
        self,
        *,
        diagnoser: Diagnoser,
        proposer: Proposer,
        validator: Validator,
        evaluator: Evaluator,
        collector: Collector | None = None,
        library: SkillLibrary | None = None,
        memory: MemoryBackend | None = None,
        memory_crystallizer: Crystallizer | None = None,
        observations: ObservationRegistry | None = None,
        pending: PendingQueue | None = None,
    ) -> None:
        self._diagnoser = diagnoser
        self._proposer = proposer
        self._validator = validator
        self._evaluator = evaluator
        self._collector = collector if collector is not None else Collector()
        self._library = library
        self._memory = memory
        self._memory_crystallizer = memory_crystallizer
        self._observations = observations if observations is not None else ObservationRegistry()
        # 候选与结论台账：身份是 candidate_id（非 id(obj)），故跨进程可驱动（见 pending.py）
        self._pending = pending if pending is not None else PendingQueue()

    def load(self) -> None:
        """加载引擎；无状态资源，no-op。"""

    def unload(self) -> None:
        """卸载引擎；无状态资源，no-op。"""

    def check(self) -> bool:
        """自检：四阶段组件齐备。"""
        return all((self._diagnoser, self._proposer, self._validator, self._evaluator))

    def run_cycle(
        self, traces: list[Trace], *, goals: Sequence[EvolutionGoal] | None = None
    ) -> EvolutionOutcome:
        """编排一次四阶段闭环。过门候选进人工确认队列（不自动发布）。

        `goals`：课程议程（可选）。显式目标（`directive`）**直接采用**、不参与归因竞争；
        其余作为诊断**先验**（权重 < 1.0 ⇒ 证据恒优先、先验只破并列）。
        """
        evidence = self._collector.collect(traces)
        if not evidence:
            return EvolutionOutcome(status="no_evidence")
        diagnosis = self._diagnose(evidence, list(goals or []))
        if diagnosis.target_plugin is None:
            return EvolutionOutcome(status="manual", diagnosis=diagnosis)
        candidate = self._proposer.propose(diagnosis)
        gate = self._validator.validate(candidate)
        if not gate.passed:
            self._pending.record(candidate, gate)
            return EvolutionOutcome(
                status="rejected", diagnosis=diagnosis, candidate=candidate, gate=gate
            )
        eval_report = self._evaluator.evaluate(candidate)
        self._pending.record(candidate, gate, eval_report)
        if eval_report.verdict == "freeze":
            # 无法评测（无绑定基准 / 无样本 / 无执行器 / 无基线）⇒ 不下发、不发布；
            # 结局**不得**记为 rollback（那是「已判退化」，无证据不得如此声称）
            return EvolutionOutcome(status="frozen", candidate=candidate, eval=eval_report)
        if eval_report.verdict != "publish":
            return EvolutionOutcome(status="rollback", candidate=candidate, eval=eval_report)
        return EvolutionOutcome(
            status="pending",
            diagnosis=diagnosis,
            candidate=candidate,
            gate=gate,
            eval=eval_report,
        )

    def _diagnose(self, evidence: list[Trace], goals: list[EvolutionGoal]) -> DiagnosisReport:
        """诊断：显式目标直采；否则把议程整体作为**先验**并入归因分数。"""
        directive = next((goal for goal in goals if goal.directive), None)
        if directive is not None:
            return DiagnosisReport(
                target_plugin=directive.plugin_id,
                issue=f"显式目标 {directive.plugin_id}（{directive.reason}）",
                evidence=[TraceRef(trace_id=t.trace_id) for t in evidence if not t.success],
                confidence=1.0,
            )
        prior = {goal.plugin_id: goal.score for goal in goals}
        return self._diagnoser.diagnose(evidence, prior=prior or None)

    def confirm(
        self, candidate: GenerationCandidate, *, approval: ApprovalTicket | None = None
    ) -> None:
        """人工确认候选，放行发布。

        ``risk_level="high"``（架构级）的候选**强制走人工审批**：须携带一张目标一致的已批准
        权限审批单，缺失/未批准/目标不符一律 fail-closed（抛 ``CONFIRM_REQUIRED``，候选保持
        ``pending``）。``risk_level="low"``（技能库级）仍须显式调用本方法——**不引入低风险自动结晶**。
        """
        if candidate.risk_level == "high":
            if approval is None or not is_approved(approval):
                raise EvolutionError(
                    EvolutionErrorCode.CONFIRM_REQUIRED,
                    f"架构级候选未获人工审批（{candidate.target_plugin}）",
                )
            if approval.request.target != candidate.target_plugin:
                raise EvolutionError(
                    EvolutionErrorCode.CONFIRM_REQUIRED,
                    f"审批单目标与候选不符（{approval.request.target} != "
                    f"{candidate.target_plugin}）",
                )
        candidate.status = "confirmed"
        self._pending.flush()

    def crystallize(self, candidate: GenerationCandidate) -> EvolutionOutcome:
        """结晶入库：须**现口径**、已确认、过验证门、留出集不退化。"""
        if candidate.caliber != GATE_CALIBER:
            # 旧口径候选：其台账结论产自**别的**判定口径（含口径字段引入前的桩口径）⇒
            # 不得投放（理由**不是**「未过门 / 退化」—— 那些判定在旧口径下并未发生）
            raise EvolutionError(
                EvolutionErrorCode.GATE_CALIBER_STALE,
                f"候选口径 {candidate.caliber} 与现口径 {GATE_CALIBER} 不符"
                f"（{candidate.target_plugin}）—— 须按现口径重新提案",
            )
        if candidate.status != "confirmed":
            raise EvolutionError(
                EvolutionErrorCode.CANDIDATE_PENDING,
                f"候选未过人工确认（{candidate.target_plugin}）",
            )
        gate = self._pending.gate_of(candidate.candidate_id)
        if gate is None or not gate.passed:
            raise EvolutionError(
                EvolutionErrorCode.GATE_REJECTED,
                f"候选未过验证门（{candidate.target_plugin}）",
            )
        eval_report = self._pending.eval_of(candidate.candidate_id)
        if eval_report is not None and eval_report.verdict == "freeze":
            # 无法评测 ≠ 退化：拿不到留出分（无基准/无样本/无执行器/无基线）⇒ 不下发，措辞据实
            raise EvolutionError(
                EvolutionErrorCode.EVAL_FROZEN,
                f"候选无法评测、未过留出评测（{candidate.target_plugin}）",
            )
        if eval_report is None or eval_report.verdict != "publish":
            raise EvolutionError(
                EvolutionErrorCode.EVAL_REGRESSED,
                f"候选未过留出评测（{candidate.target_plugin}）",
            )
        outcome = (
            self._crystallize_skill(candidate)
            if candidate.kind == "skill"
            else self._crystallize_plugin(candidate)
        )
        # 结晶发布即开启观察期（基线 = 该候选的留出评测分）：发布后由 observe() 持续采样
        self.observations.open(candidate.target_plugin, baseline=eval_report.held_out_score)
        return outcome

    def observe(
        self, target: str, score: float, *, now: float | None = None
    ) -> EvolutionOutcome | None:
        """观察期采样：回归超阈值 → 自动溶解 + 冻结该方向（返回 ``dissolved`` 结局）。

        未开窗目标 / 未达判定门 / 冻结期内一律返回 ``None``（不抛异常）；回归证据随教训条目留痕。
        """
        if not self._observations.sample(target, score, now=now):
            return None
        window = self._observations.window(target)
        if window is None:  # 理论不可达（sample 命中即已开窗）
            return None
        self.dissolve(
            target,
            f"观察期回归：均分 {window.mean:.3f} < 基线 {window.baseline:.3f} - 容差，"
            f"样本 {len(window.samples)} 条",
        )
        self._observations.freeze(target, now=now)
        return EvolutionOutcome(status="dissolved", skill_id=f"skills.evolution.{target}")

    @property
    def observations(self) -> ObservationRegistry:
        """观察期窗口注册表（发布后回归采样的状态面）。"""
        return self._observations

    def dissolve(self, plugin_id: str, reason: str) -> None:
        """溶解退化：技能标 deprecated，教训写回 L2。"""
        skill_id = f"skills.evolution.{plugin_id}"
        if self._library is not None:
            with contextlib.suppress(KeyError):
                self._library.lookup(skill_id).status = "deprecated"
        if self._memory is not None:
            self._memory.put(
                MemoryEntry(
                    id=f"evolution.dissolve.{plugin_id}",
                    layer="L2",
                    content=reason,
                    tags=["evolution", "dissolve"],
                    source="evolution",
                    trace_id="evolution",
                )
            )

    def pending(self) -> list[GenerationCandidate]:
        """待人工确认队列快照（只含 ``status="pending"`` 的候选）。"""
        return self._pending.pending()

    def find(self, candidate_id: str) -> GenerationCandidate | None:
        """按稳定身份定位候选（供操作面驱动；不存在返回 ``None``）。"""
        return self._pending.find(candidate_id)

    def reject(self, candidate: GenerationCandidate, *, reason: str | None = None) -> None:
        """人工拒绝候选：置 ``rejected`` 并落盘（留 L2 教训），后续发布被拒。"""
        candidate.status = "rejected"
        self._pending.flush()
        if self._memory is not None and reason:
            self._memory.put(
                MemoryEntry(
                    id=f"evolution.rejected.{candidate.candidate_id}",
                    layer="L2",
                    content=f"候选被拒（{candidate.target_plugin}）：{reason}",
                    tags=["evolution", "reject"],
                    source="evolution",
                    trace_id="evolution",
                )
            )

    def _crystallize_skill(self, candidate: GenerationCandidate) -> EvolutionOutcome:
        skill = Skill(
            skill_id=f"skills.evolution.{candidate.target_plugin}",
            description=candidate.delta.get("issue", ""),
            param_schema=candidate.delta.get("schema", {}),
            status="active",
        )
        if self._library is not None:
            self._library.register(skill)
        return EvolutionOutcome(status="published", candidate=candidate, skill_id=skill.skill_id)

    def _crystallize_plugin(self, candidate: GenerationCandidate) -> EvolutionOutcome:
        if self._memory_crystallizer is not None:
            self._memory_crystallizer.crystallize(
                MemoryEntry(
                    id=f"evolution.candidate.{candidate.generation}",
                    layer="L3",
                    content=candidate.delta.get("issue", ""),
                    tags=["evolution", "candidate"],
                    source="evolution",
                    trace_id="evolution",
                )
            )
        # 结局诚实：架构级候选只「批准登记」，不产出任何可发布产物 ⇒ 不谎报 published
        return EvolutionOutcome(status="accepted", candidate=candidate)


class EvolutionTrigger:
    """进化触发器：累计 N 轮或强制触发；后台低优先级执行。"""

    def __init__(self, *, threshold: int = 10) -> None:
        self._threshold = threshold
        self._count = 0

    def maybe_run(self, traces: list[Trace], *, force: bool = False) -> bool:
        self._count += 1
        return force or self._count >= self._threshold

    def reset(self) -> None:
        self._count = 0
