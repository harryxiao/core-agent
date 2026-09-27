"""进化引擎（evolution）—— 四阶段结晶闭环编排。

`EvolutionEngine` 是进化层唯一满足 `Plugin` 契约的实体：编排
诊断 → 提案 → 验证门 → 留出评测，过门候选进人工确认队列，`confirm()` +
`crystallize()` 落库发布，退化时 `dissolve()` 溶解回退。`EvolutionTrigger`
按累计轮次 / 强制触发进化，后台低优先级执行。

对应接口：doc/03-interfaces/evolution-interface.md ｜ 规格 evolution/spec.md
"""

from __future__ import annotations

import contextlib
from typing import Any

from core.memory import Crystallizer, MemoryBackend, MemoryEntry
from core.skills import Skill, SkillLibrary

from .collector import Collector
from .diagnoser import Diagnoser
from .errors import EvolutionError, EvolutionErrorCode
from .evaluator import Evaluator
from .models import (
    EvalReport,
    EvolutionOutcome,
    GateReport,
    GenerationCandidate,
    Trace,
)
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
    ) -> None:
        self._diagnoser = diagnoser
        self._proposer = proposer
        self._validator = validator
        self._evaluator = evaluator
        self._collector = collector if collector is not None else Collector()
        self._library = library
        self._memory = memory
        self._memory_crystallizer = memory_crystallizer
        self._pending: list[GenerationCandidate] = []
        self._gate: dict[int, GateReport] = {}
        self._eval: dict[int, EvalReport] = {}

    def load(self) -> None:
        """加载引擎；无状态资源，no-op。"""

    def unload(self) -> None:
        """卸载引擎；无状态资源，no-op。"""

    def check(self) -> bool:
        """自检：四阶段组件齐备。"""
        return all((self._diagnoser, self._proposer, self._validator, self._evaluator))

    def run_cycle(self, traces: list[Trace]) -> EvolutionOutcome:
        """编排一次四阶段闭环。过门候选进人工确认队列（不自动发布）。"""
        evidence = self._collector.collect(traces)
        if not evidence:
            return EvolutionOutcome(status="no_evidence")
        diagnosis = self._diagnoser.diagnose(evidence)
        if diagnosis.target_plugin is None:
            return EvolutionOutcome(status="manual", diagnosis=diagnosis)
        candidate = self._proposer.propose(diagnosis)
        gate = self._validator.validate(candidate)
        self._gate[id(candidate)] = gate
        if not gate.passed:
            return EvolutionOutcome(
                status="rejected", diagnosis=diagnosis, candidate=candidate, gate=gate
            )
        eval_report = self._evaluator.evaluate(candidate)
        self._eval[id(candidate)] = eval_report
        if eval_report.verdict != "publish":
            return EvolutionOutcome(status="rollback", candidate=candidate, eval=eval_report)
        self._pending.append(candidate)
        return EvolutionOutcome(
            status="pending",
            diagnosis=diagnosis,
            candidate=candidate,
            gate=gate,
            eval=eval_report,
        )

    def confirm(self, candidate: GenerationCandidate) -> None:
        """人工确认候选，放行发布。"""
        candidate.status = "confirmed"

    def crystallize(self, candidate: GenerationCandidate) -> EvolutionOutcome:
        """结晶入库：须已确认、过验证门、留出集不退化。"""
        if candidate.status != "confirmed":
            raise EvolutionError(
                EvolutionErrorCode.CANDIDATE_PENDING,
                f"候选未过人工确认（{candidate.target_plugin}）",
            )
        gate = self._gate.get(id(candidate))
        if gate is None or not gate.passed:
            raise EvolutionError(
                EvolutionErrorCode.GATE_REJECTED,
                f"候选未过验证门（{candidate.target_plugin}）",
            )
        eval_report = self._eval.get(id(candidate))
        if eval_report is None or eval_report.verdict != "publish":
            raise EvolutionError(
                EvolutionErrorCode.EVAL_REGRESSED,
                f"候选留出集退化（{candidate.target_plugin}）",
            )
        if candidate.kind == "skill":
            return self._crystallize_skill(candidate)
        return self._crystallize_plugin(candidate)

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
        """人工确认队列快照。"""
        return list(self._pending)

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
        return EvolutionOutcome(status="published", candidate=candidate)


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
