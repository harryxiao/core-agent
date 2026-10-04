"""evolution 单元测试（对齐 M4 验收锚点 + evolution-interface 契约红线）。

覆盖：无证据采集 / 提案待确认 / 验证门阻断 / 留出集退化回滚 / 归因 / 并发上限 /
端到端结晶闭环 / 触发 / 溶解。
"""

from __future__ import annotations

import asyncio

import pytest

from core.evolution import (
    Benchmark,
    BenchmarkRegistry,
    Collector,
    Diagnoser,
    DiagnosisReport,
    EvalReport,
    Evaluator,
    EvolutionEngine,
    EvolutionError,
    EvolutionErrorCode,
    EvolutionTrigger,
    GenerationCandidate,
    Proposer,
    QualityEvaluator,
    Trace,
    Validator,
)
from core.permission import ApprovalRequest, ApprovalTicket, ApprovalWorkflow
from core.skills import Skill, SkillLibrary


def _trace(
    trace_id: str,
    *,
    success: bool,
    plugin_id: str | None = None,
    result: object = "ok",
) -> Trace:
    return Trace(
        trace_id=trace_id,
        task_type="t",
        action={"a": 1},
        result=result,
        success=success,
        plugin_id=plugin_id,
    )


def _engine(  # noqa: PLR0913 — 测试构造辅助
    *,
    library: SkillLibrary | None = None,
    validator: Validator | None = None,
    evaluator: Evaluator | None = None,
    diagnoser: Diagnoser | None = None,
    proposer: Proposer | None = None,
    memory: object | None = None,
) -> EvolutionEngine:
    return EvolutionEngine(
        diagnoser=diagnoser or Diagnoser(),
        proposer=proposer or Proposer(),
        validator=validator or Validator(),
        evaluator=evaluator or Evaluator(),
        library=library,
        memory=memory,  # type: ignore[arg-type]
    )


# ---- 采集：无证据不采集 ----


def test_collector_skips_no_evidence() -> None:
    traces = [
        _trace("1", success=True, plugin_id="memory.retrieve"),
        _trace("2", success=False, plugin_id="memory.retrieve", result=None),
        _trace("3", success=False, plugin_id="memory.retrieve"),
    ]
    collected = Collector().collect(traces)
    assert [t.trace_id for t in collected] == ["1", "3"]


def test_collector_require_evidence_raises_no_evidence() -> None:
    traces = [_trace("1", success=False, plugin_id="memory.retrieve", result=None)]
    with pytest.raises(EvolutionError) as exc_info:
        Collector().collect(traces, require_evidence=True)
    assert exc_info.value.code is EvolutionErrorCode.NO_EVIDENCE


# ---- 提案：待人工确认，不自动发布 ----


def test_propose_pending_no_autopublish() -> None:
    diagnosis = DiagnosisReport(target_plugin="memory.retrieve", issue="检索失败")
    candidate = Proposer().propose(diagnosis)
    assert candidate.status == "pending"
    assert candidate.kind == "skill"
    assert candidate.target_plugin == "memory.retrieve"


# ---- 验证门：GATE_REJECTED 阻断发布 ----


def test_gate_rejected_blocks_publish() -> None:
    library = SkillLibrary()
    engine = _engine(library=library, validator=Validator(review=lambda _: False))
    outcome = engine.run_cycle([_trace("1", success=False, plugin_id="memory.retrieve")])
    assert outcome.status == "rejected"
    assert outcome.candidate is not None
    engine.confirm(outcome.candidate)
    with pytest.raises(EvolutionError) as exc_info:
        engine.crystallize(outcome.candidate)
    assert exc_info.value.code is EvolutionErrorCode.GATE_REJECTED
    assert library.all_skills() == []


# ---- 留出集退化：EVAL_REGRESSED 触发回滚 ----


def test_eval_regressed_triggers_rollback() -> None:
    registry = BenchmarkRegistry()
    registry.set_baseline("memory.retrieve", 1.0)
    evaluator = Evaluator(registry=registry, score_fn=lambda _c: 0.0)
    engine = _engine(evaluator=evaluator)
    outcome = engine.run_cycle([_trace("1", success=False, plugin_id="memory.retrieve")])
    assert outcome.status == "rollback"
    assert outcome.eval is not None and outcome.eval.verdict == "rollback"
    assert outcome.candidate is not None
    engine.confirm(outcome.candidate)
    with pytest.raises(EvolutionError) as exc_info:
        engine.crystallize(outcome.candidate)
    assert exc_info.value.code is EvolutionErrorCode.EVAL_REGRESSED


# ---- 归因：插件级归因 / 无法归因走 manual ----


def test_diagnoser_attributes_to_single_plugin() -> None:
    traces = [
        _trace("1", success=False, plugin_id="memory.retrieve"),
        _trace("2", success=False, plugin_id="memory.retrieve"),
    ]
    report = Diagnoser().diagnose(traces)
    assert report.target_plugin == "memory.retrieve"


def test_diagnoser_no_attribution_goes_manual() -> None:
    traces = [
        _trace("1", success=False, plugin_id="memory.retrieve"),
        _trace("2", success=False, plugin_id="tools.exec"),
    ]
    engine = _engine()
    outcome = engine.run_cycle(traces)
    assert outcome.status == "manual"


# ---- 并发评测：Semaphore 限流 ----


class _ConcurrencyTracker:
    def __init__(self) -> None:
        self.active = 0
        self.peak = 0

    def enter(self) -> None:
        self.active += 1
        self.peak = max(self.peak, self.active)

    def exit(self) -> None:
        self.active -= 1


class _TrackingEvaluator(Evaluator):
    def __init__(self, tracker: _ConcurrencyTracker, max_concurrency: int) -> None:
        super().__init__(max_concurrency=max_concurrency)
        self._tracker = tracker

    async def aevaluate(self, candidate: GenerationCandidate) -> EvalReport:
        self._tracker.enter()
        await asyncio.sleep(0.01)
        result = await super().aevaluate(candidate)
        self._tracker.exit()
        return result


def test_evaluator_concurrency_limited() -> None:
    tracker = _ConcurrencyTracker()
    evaluator = _TrackingEvaluator(tracker, max_concurrency=2)
    candidates = [
        GenerationCandidate(generation=i, target_plugin="p", delta={}, kind="skill")
        for i in range(6)
    ]
    asyncio.run(evaluator.evaluate_batch(candidates))
    assert tracker.peak == 2  # noqa: PLR2004 — 并发峰值断言常量


# ---- 端到端：完整结晶闭环 ----


def test_end_to_end_crystallize_publish() -> None:
    library = SkillLibrary()
    engine = _engine(library=library)
    outcome = engine.run_cycle([_trace("1", success=False, plugin_id="memory.retrieve")])
    assert outcome.status == "pending"
    assert library.all_skills() == []  # 未确认前不发布
    assert outcome.candidate is not None
    engine.confirm(outcome.candidate)
    result = engine.crystallize(outcome.candidate)
    assert result.status == "published"
    assert result.skill_id == "skills.evolution.memory.retrieve"
    assert library.lookup(result.skill_id) is not None


# ---- 评测基建：基准集 + 三维质量 ----


def test_benchmark_registry_register_and_baseline() -> None:
    registry = BenchmarkRegistry()
    registry.register(
        Benchmark(
            benchmark_id="b1", task_type="retrieval", samples=[{"input": "x", "expected": "y"}]
        )
    )
    registry.set_baseline("memory.retrieve", 0.8)
    assert registry.benchmark_for("retrieval") is not None
    assert registry.benchmark_for("retrieval").benchmark_id == "b1"
    assert registry.benchmark_for("unknown") is None
    assert registry.baseline_score("memory.retrieve") == 0.8  # noqa: PLR2004 — 基线分常量
    assert registry.baseline_score("unknown") == 0.0


def test_quality_evaluator_three_dimensions() -> None:
    report = QualityEvaluator().score(
        goal_reached=True,
        result="ok",
        expected="ok",
        trajectory=[{"failed": False}, {"failed": True}],
    )
    assert report.completion == 1.0
    assert report.correctness == 1.0
    assert report.trajectory == 0.5  # noqa: PLR2004 — 轨迹分期望值


# ---- 触发 + 溶解 ----


def test_trigger_maybe_run_threshold_and_force() -> None:
    trigger = EvolutionTrigger(threshold=3)
    traces: list[Trace] = []
    assert trigger.maybe_run(traces) is False
    assert trigger.maybe_run(traces) is False
    assert trigger.maybe_run(traces) is True
    trigger.reset()
    assert trigger.maybe_run(traces, force=True) is True


class _SpyBackend:
    def __init__(self) -> None:
        self.put_entries: list[object] = []

    def put(self, entry: object) -> None:
        self.put_entries.append(entry)


def test_dissolve_deprecates_skill_and_writes_lesson() -> None:
    library = SkillLibrary()
    library.register(
        Skill(skill_id="skills.evolution.memory.retrieve", description="", param_schema={})
    )
    backend = _SpyBackend()
    engine = _engine(library=library, memory=backend)
    engine.dissolve("memory.retrieve", "留出集退化")
    assert library.lookup("skills.evolution.memory.retrieve").status == "deprecated"
    assert len(backend.put_entries) == 1
    assert backend.put_entries[0].layer == "L2"


# ---- HITL confirm 门（0046：架构级候选强制人工审批）----


def _pending(engine: EvolutionEngine) -> GenerationCandidate:
    """跑一次闭环得到过门候选（status="pending"）。"""
    outcome = engine.run_cycle([_trace("1", success=False, plugin_id="memory.retrieve")])
    assert outcome.status == "pending" and outcome.candidate is not None
    return outcome.candidate


def _ticket(target: str, *, approved: bool = True) -> ApprovalTicket:
    """造一张目标为 target 的审批单（经审批流真实流转）。"""
    workflow = ApprovalWorkflow()
    ticket = workflow.create(
        ApprovalRequest(
            op="evolution.crystallize",
            target=target,
            impact_summary="架构级候选结晶",
            rollback_plan="dissolve 回 L3",
            trace_id="evolution",
        )
    )
    if approved:
        workflow.approve(ticket, approver="alice")
    else:
        workflow.reject(ticket, note="不可逆，退回")
    return ticket


def test_proposer_marks_risk_level_by_kind() -> None:
    """风险域由提案阶段按 kind 固化：plugin → high，skill → low。"""
    diagnosis = DiagnosisReport(target_plugin="memory.retrieve", issue="x")
    assert Proposer(kind="plugin").propose(diagnosis).risk_level == "high"
    assert Proposer(kind="skill").propose(diagnosis).risk_level == "low"


def test_high_risk_candidate_without_approval_stays_pending() -> None:
    engine = _engine(proposer=Proposer(kind="plugin"))
    candidate = _pending(engine)
    with pytest.raises(EvolutionError) as exc_info:
        engine.confirm(candidate)
    assert exc_info.value.code is EvolutionErrorCode.CONFIRM_REQUIRED
    assert candidate.status == "pending"
    with pytest.raises(EvolutionError) as exc_info:
        engine.crystallize(candidate)
    assert exc_info.value.code is EvolutionErrorCode.CANDIDATE_PENDING


def test_high_risk_candidate_confirms_with_approved_ticket() -> None:
    library = SkillLibrary()
    engine = _engine(library=library, proposer=Proposer(kind="plugin"))
    candidate = _pending(engine)
    engine.confirm(candidate, approval=_ticket(candidate.target_plugin))
    assert candidate.status == "confirmed"
    assert engine.crystallize(candidate).status == "published"


def test_rejected_approval_blocks_high_risk_candidate() -> None:
    engine = _engine(proposer=Proposer(kind="plugin"))
    candidate = _pending(engine)
    with pytest.raises(EvolutionError) as exc_info:
        engine.confirm(candidate, approval=_ticket(candidate.target_plugin, approved=False))
    assert exc_info.value.code is EvolutionErrorCode.CONFIRM_REQUIRED
    assert candidate.status == "pending"


def test_approval_target_mismatch_blocks_confirm() -> None:
    """别的插件的批准单不得解锁本候选。"""
    engine = _engine(proposer=Proposer(kind="plugin"))
    candidate = _pending(engine)
    assert candidate.target_plugin == "memory.retrieve"
    with pytest.raises(EvolutionError) as exc_info:
        engine.confirm(candidate, approval=_ticket("memory.write"))
    assert exc_info.value.code is EvolutionErrorCode.CONFIRM_REQUIRED
    assert candidate.status == "pending"


def test_low_risk_candidate_confirms_without_ticket() -> None:
    """技能库级候选仍须显式 confirm，但不要求权限工单（不引入低风险自动结晶）。"""
    library = SkillLibrary()
    engine = _engine(library=library)
    candidate = _pending(engine)
    assert candidate.risk_level == "low"
    with pytest.raises(EvolutionError) as exc_info:
        engine.crystallize(candidate)
    assert exc_info.value.code is EvolutionErrorCode.CANDIDATE_PENDING
    engine.confirm(candidate)
    assert engine.crystallize(candidate).status == "published"
