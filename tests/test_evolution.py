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
    EvolutionGoal,
    EvolutionTrigger,
    EvolutionWorker,
    GenerationCandidate,
    ObservationRegistry,
    ObservationWindow,
    Proposer,
    QualityEvaluator,
    Trace,
    Validator,
)
from core.observability import TraceEvent, TraceLogger, Tracer
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
    observations: ObservationRegistry | None = None,
) -> EvolutionEngine:
    return EvolutionEngine(
        diagnoser=diagnoser or Diagnoser(),
        proposer=proposer or Proposer(),
        validator=validator or Validator(),
        evaluator=evaluator or Evaluator(),
        library=library,
        memory=memory,  # type: ignore[arg-type]
        observations=observations,
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
    # 架构级结晶：批准登记即止，无产物发布 ⇒ 结局为 accepted（不谎报 published）
    assert engine.crystallize(candidate).status == "accepted"


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


# ---- 观察期回归自动溶解（0047）----


def _published(engine: EvolutionEngine) -> str:
    """跑完整闭环并确认发布，返回观察目标（= 候选 target_plugin）。"""
    candidate = _pending(engine)
    engine.confirm(candidate)
    assert engine.crystallize(candidate).status == "published"
    return candidate.target_plugin


def test_observation_open_and_mean() -> None:
    registry = ObservationRegistry()
    window = registry.open("memory.retrieve", baseline=1.0)
    assert isinstance(window, ObservationWindow)
    assert registry.window("memory.retrieve") is window
    assert window.mean == 0.0  # 无样本
    assert registry.window("nope") is None


def test_observation_ignores_unopened_target() -> None:
    """未开窗目标的采样被忽略：不建窗、不触发。"""
    registry = ObservationRegistry()
    assert registry.sample("memory.retrieve", 0.0) is False
    assert registry.window("memory.retrieve") is None


def test_observation_below_min_samples_not_regressed() -> None:
    """样本不足不判定（单点暴跌不算）。"""
    registry = ObservationRegistry()
    registry.open("memory.retrieve", baseline=1.0)
    assert registry.sample("memory.retrieve", 0.0) is False
    assert registry.sample("memory.retrieve", 0.0) is False
    assert registry.window("memory.retrieve").samples == [0.0, 0.0]


def test_observation_regression_triggers_at_threshold() -> None:
    """样本达下限且均分低于「基线 − 容差」→ 触发。"""
    registry = ObservationRegistry()
    registry.open("memory.retrieve", baseline=1.0)
    assert registry.sample("memory.retrieve", 0.9) is False
    assert registry.sample("memory.retrieve", 0.6) is False
    assert registry.sample("memory.retrieve", 0.1) is True  # 均分 0.533 < 0.8


def test_observation_no_regression_keeps_window() -> None:
    registry = ObservationRegistry()
    registry.open("memory.retrieve", baseline=1.0)
    for _ in range(4):
        assert registry.sample("memory.retrieve", 0.9) is False


def test_observation_freeze_blocks_then_expires() -> None:
    """冻结期（冷却）内不累积不触发；冷却期结束恢复采样。"""
    registry = ObservationRegistry(cooldown_s=100.0)
    registry.open("memory.retrieve", baseline=1.0)
    registry.freeze("memory.retrieve", now=1000.0)
    assert registry.window("memory.retrieve").samples == []  # 冻结即清零
    for _ in range(3):
        assert registry.sample("memory.retrieve", 0.0, now=1050.0) is False
    assert registry.window("memory.retrieve").samples == []  # 冻结期内不累积
    assert registry.sample("memory.retrieve", 0.0, now=1100.0) is False  # 冷却结束恢复累积
    assert registry.window("memory.retrieve").samples == [0.0]
    assert registry.sample("memory.retrieve", 0.0, now=1101.0) is False
    assert registry.sample("memory.retrieve", 0.0, now=1102.0) is True  # 达下限 + 越线


def test_crystallize_opens_observation_window() -> None:
    """结晶发布后开窗（基线 = 该候选评测分）。"""
    engine = _engine(library=SkillLibrary())
    target = _published(engine)
    window = engine.observations.window(target)
    assert window is not None and window.baseline == 0.0


def test_observe_regression_auto_dissolves_with_lesson() -> None:
    library = SkillLibrary()
    backend = _SpyBackend()
    engine = _engine(library=library, memory=backend)
    target = _published(engine)
    window = engine.observations.window(target)
    assert window is not None
    window.baseline = 1.0  # 直接给个有意义的基线（默认评测分 0.0）

    assert engine.observe(target, 0.9) is None
    assert engine.observe(target, 0.5) is None
    outcome = engine.observe(target, 0.0)

    assert outcome is not None and outcome.status == "dissolved"
    assert library.lookup(f"skills.evolution.{target}").status == "deprecated"
    lesson = backend.put_entries[-1]
    assert lesson.layer == "L2"
    assert "基线 1.000" in lesson.content and "均分 0.467" in lesson.content
    assert "样本 3" in lesson.content


def test_observe_unopened_target_and_no_regression() -> None:
    """未开窗 → None（不抛）；未回归 → None 且技能保持 active。"""
    library = SkillLibrary()
    engine = _engine(library=library)
    assert engine.observe("memory.retrieve", 0.0) is None
    target = _published(engine)
    window = engine.observations.window(target)
    assert window is not None
    window.baseline = 0.1
    for _ in range(3):
        assert engine.observe(target, 0.9) is None
    assert library.lookup(f"skills.evolution.{target}").status == "active"


# ---- 冷路径驱动 + 窗口持久化 + 批次采样（0051）----


def _worker_engine(registry: ObservationRegistry, **kw: object) -> tuple[EvolutionWorker, Tracer]:
    """造一个「tracer + worker + 指定窗口注册表」的冷路径装置。"""
    tracer = Tracer()
    engine = _engine(observations=registry, **kw)  # type: ignore[arg-type]
    return EvolutionWorker(tracer=tracer, engine=engine), tracer


def _log_tool(tracer: Tracer, trace_id: str, tool: str, *, ok: bool) -> None:
    TraceLogger(tracer).log_tool_call(trace_id, tool, {}, {"ok": ok}, 1.0)


def test_observation_window_persists_across_restart(tmp_path) -> None:
    path = tmp_path / "observations.json"
    registry = ObservationRegistry(path=path, cooldown_s=100.0)
    registry.open("memory.retrieve", baseline=1.0)
    registry.sample("memory.retrieve", 0.9, now=1000.0)
    registry.freeze("memory.retrieve", now=1000.0)

    revived = ObservationRegistry(path=path, cooldown_s=100.0)
    window = revived.window("memory.retrieve")

    assert window is not None
    assert (window.baseline, window.samples, window.frozen_until) == (1.0, [], 1100.0)
    assert revived.sample("memory.retrieve", 0.0, now=1050.0) is False, "冻结期跨进程仍有效"


def test_observation_registry_pure_memory_without_path(tmp_path) -> None:
    registry = ObservationRegistry()
    registry.open("memory.retrieve", baseline=1.0)
    registry.sample("memory.retrieve", 0.0)

    assert list(tmp_path.iterdir()) == [], "未注入路径 → 不落盘"


def test_observation_registry_corrupt_state_degrades(tmp_path) -> None:
    path = tmp_path / "observations.json"
    path.write_text("{ not json", encoding="utf-8")

    registry = ObservationRegistry(path=path)

    assert registry.window("memory.retrieve") is None, "损坏落盘 → 无窗口（不抛）"
    registry.open("memory.retrieve", baseline=1.0)
    assert ObservationRegistry(path=path).window("memory.retrieve") is not None


def test_worker_samples_open_windows_by_plugin() -> None:
    """每轮 cycle 后按 plugin_id 归因上报批次成功率；无归因的目标不采样。"""
    registry = ObservationRegistry()
    registry.open("memory.retrieve", baseline=1.0)
    registry.open("tools.web_fetch", baseline=1.0)
    worker, tracer = _worker_engine(registry)
    trace_id = tracer.start_trace("t1")
    _log_tool(tracer, trace_id, "memory.retrieve", ok=False)
    _log_tool(tracer, trace_id, "memory.retrieve", ok=True)
    worker.on_trace_complete(trace_id)

    worker.maybe_run(force=True)

    assert registry.window("memory.retrieve").samples == [0.5]  # noqa: PLR2004 — 1/2 成功
    assert registry.window("tools.web_fetch").samples == [], "无归因 trace 不采样"


def test_worker_sampling_drives_auto_dissolve() -> None:
    """批次成功率连续低于基线 → 达下限即自动溶解（端到端：采样来源 → observe → dissolve）。"""
    library = SkillLibrary()
    backend = _SpyBackend()
    registry = ObservationRegistry()
    engine = _engine(library=library, memory=backend, observations=registry)
    target = _published(engine)
    window = registry.window(target)
    assert window is not None
    window.baseline = 1.0  # 直接给个有意义的基线（默认评测分 0.0）

    tracer = Tracer()
    worker = EvolutionWorker(tracer=tracer, engine=engine)
    for i in range(3):
        trace_id = tracer.start_trace(f"t{i}")
        _log_tool(tracer, trace_id, target, ok=False)  # 批次成功率 0.0
        worker.on_trace_complete(trace_id)
        worker.maybe_run(force=True)

    assert library.lookup(f"skills.evolution.{target}").status == "deprecated", "回归即自动溶解"
    assert "基线 1.000" in backend.put_entries[-1].content


# ---- 自动课程：先验解并列 / 显式目标直采（change 0084）----


def test_diagnoser_tie_without_prior_stays_manual() -> None:
    """无先验时行为不变：并列仍转人工（回归基线）。"""
    report = Diagnoser().diagnose(
        [_trace("a", success=False, plugin_id="A"), _trace("b", success=False, plugin_id="B")]
    )
    assert report.target_plugin is None
    assert "并列" in report.issue


def test_diagnoser_prior_breaks_tie() -> None:
    """课程先验的唯一作用：解并列。"""
    report = Diagnoser().diagnose(
        [_trace("a", success=False, plugin_id="A"), _trace("b", success=False, plugin_id="B")],
        prior={"A": 0.5},
    )
    assert report.target_plugin == "A"


def test_prior_never_overrides_evidence() -> None:
    """先验权重 < 1.0（证据每条 1.0）⇒ 多一条失败证据即压过先验。"""
    report = Diagnoser().diagnose(
        [_trace("b1", success=False, plugin_id="B"), _trace("b2", success=False, plugin_id="B")],
        prior={"A": 0.5},
    )
    assert report.target_plugin == "B"


def test_run_cycle_directive_goal_targets_given_plugin() -> None:
    """显式目标是**指令**：证据指向 B，本轮目标仍是 A（仍走完整四阶段）。"""
    outcome = _engine().run_cycle(
        [_trace("b", success=False, plugin_id="B")],
        goals=[EvolutionGoal("A", 1.0, "显式指定目标", directive=True)],
    )
    assert outcome.status == "pending"
    assert outcome.candidate is not None
    assert outcome.candidate.target_plugin == "A"


def test_worker_auto_agenda_breaks_tie() -> None:
    """生产默认开课：并列失败由课程议程解并列（不再一律转人工）。"""
    worker, tracer = _worker_engine(ObservationRegistry())
    trace_id = tracer.start_trace("t1")
    _log_tool(tracer, trace_id, "memory.retrieve", ok=False)
    _log_tool(tracer, trace_id, "tools.web_fetch", ok=False)
    worker.on_trace_complete(trace_id)

    outcome = worker.maybe_run(force=True)

    assert outcome is not None
    assert outcome.status != "manual"
    assert outcome.candidate is not None
    assert outcome.candidate.target_plugin == "memory.retrieve", "并列以 plugin_id 升序在先"


def test_worker_explicit_goal_overrides_evidence() -> None:
    worker, tracer = _worker_engine(ObservationRegistry())
    trace_id = tracer.start_trace("t1")
    _log_tool(tracer, trace_id, "memory.retrieve", ok=False)
    worker.on_trace_complete(trace_id)

    outcome = worker.maybe_run(force=True, goal="tools.web_fetch")

    assert outcome is not None
    assert outcome.candidate is not None
    assert outcome.candidate.target_plugin == "tools.web_fetch"


class _NoAgenda:
    """空议程规划器：证明先验确实来自**注入的课程**（无先验 ⇒ 行为同既有）。"""

    def plan(self, *_args: object, **_kwargs: object) -> list[EvolutionGoal]:
        return []


def test_worker_curriculum_is_injectable() -> None:
    """课程可替换（缺省自建）：空议程 ⇒ 无先验 ⇒ 并列仍转人工。"""
    tracer = Tracer()
    worker = EvolutionWorker(
        tracer=tracer,
        engine=_engine(),
        planner=_NoAgenda(),  # type: ignore[arg-type] — 注入面只要求 plan()
    )
    trace_id = tracer.start_trace("t1")
    _log_tool(tracer, trace_id, "memory.retrieve", ok=False)
    _log_tool(tracer, trace_id, "tools.web_fetch", ok=False)
    worker.on_trace_complete(trace_id)

    assert worker.maybe_run(force=True).status == "manual"


# ---- 模块归因采集通道（change 0101） ----


def _module_event(trace_id: str, module_id: str, *, failed: bool) -> TraceEvent:
    return TraceEvent(
        trace_id=trace_id,
        span_id="s1",
        ts=0.0,
        kind="loop_finished",
        payload={"reply": "LOOP_LIMIT_EXCEEDED", "failed": failed},
        module_id=module_id,
    )


def test_worker_adapts_module_attributed_event() -> None:
    """带模块归因的事件 ⇒ 适配为可归因到该模块的 Trace（架构模块自身失败成为证据）。"""
    worker, tracer = _worker_engine(ObservationRegistry())
    trace_id = tracer.start_trace("t1")
    tracer.record(_module_event(trace_id, "loop.default", failed=True))

    traces = worker._to_traces(tracer.replay(trace_id))  # noqa: SLF001 — 适配器单测

    assert len(traces) == 1
    assert traces[0].plugin_id == "loop.default", "按 module_id 归因到架构模块"
    assert traces[0].success is False, "失败事件 ⇒ success 为假"
    assert traces[0].task_type == "module_health"


def test_worker_module_attribution_drives_diagnosis() -> None:
    """端到端：模块归因事件经采集 ⇒ 诊断归因到该模块（loop.default）。"""
    worker, tracer = _worker_engine(ObservationRegistry())
    trace_id = tracer.start_trace("t1")
    tracer.record(_module_event(trace_id, "loop.default", failed=True))
    worker.on_trace_complete(trace_id)

    outcome = worker.maybe_run(force=True)

    assert outcome is not None and outcome.candidate is not None
    assert outcome.candidate.target_plugin == "loop.default"


def test_worker_success_module_event_is_not_a_defect() -> None:
    """带归因的**成功**事件不产缺陷证据（success=True）。"""
    worker, tracer = _worker_engine(ObservationRegistry())
    trace_id = tracer.start_trace("t1")
    tracer.record(_module_event(trace_id, "loop.default", failed=False))

    traces = worker._to_traces(tracer.replay(trace_id))  # noqa: SLF001 — 适配器单测

    assert traces and traces[0].success is True


def test_worker_tool_channel_unchanged() -> None:
    """既有工具通道逐字不变：仍按工具 id 归因、仍产 `tool_use` 类证据。"""
    worker, tracer = _worker_engine(ObservationRegistry())
    trace_id = tracer.start_trace("t1")
    _log_tool(tracer, trace_id, "tools.echo", ok=False)

    traces = worker._to_traces(tracer.replay(trace_id))  # noqa: SLF001 — 适配器单测

    assert len(traces) == 1
    assert traces[0].plugin_id == "tools.echo"
    assert traces[0].task_type == "tool_use"


# ---- trace 快照采集与批窗口有界（change 0103） ----


def test_worker_snapshots_events_at_callback_time() -> None:
    """回调时刻取快照：封口释放内存后仍可采集（0101/0102 回归守护）。"""
    worker, tracer = _worker_engine(ObservationRegistry())
    trace_id = tracer.start_trace("t1")
    _log_tool(tracer, trace_id, "tools.echo", ok=False)
    worker.on_trace_complete(trace_id)

    tracer.end_trace(trace_id)  # 封口：Tracer 释放内存

    assert tracer.replay(trace_id) == [], "封口后 Tracer 不再驻留"
    assert [t.plugin_id for t in worker._collect()] == ["tools.echo"], "快照仍可采集"  # noqa: SLF001


def test_completed_batch_window_is_bounded() -> None:
    """`_completed` 受批窗口约束：未达阈值累积、真跑一轮后清空（批语义不变）。"""
    worker, tracer = _worker_engine(ObservationRegistry())
    for i in range(9):
        trace_id = tracer.start_trace(f"t{i}")
        _log_tool(tracer, trace_id, "tools.echo", ok=False)
        worker.on_trace_complete(trace_id)
        worker.maybe_run()  # 未达阈值（第 10 次才真跑）

    assert len(worker._completed) == 9, "批窗口内累积、不无界增长"  # noqa: PLR2004, SLF001

    trace_id = tracer.start_trace("t9")
    _log_tool(tracer, trace_id, "tools.echo", ok=False)
    worker.on_trace_complete(trace_id)
    worker.maybe_run()  # 第 10 次 ⇒ 真跑一轮

    assert worker._completed == [], "真跑一轮后清空"  # noqa: SLF001
