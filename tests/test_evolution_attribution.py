"""归因驱动提案与结晶语义诚实化（change 0102）。

覆盖：候选 `kind` 由诊断归因驱动（内部核心模块 ⇒ `plugin`/`high`，否则 ⇒ `skill`/`low`）、
显式覆盖优先于归因、归因白名单与仓内 `plugin_id` 声明一致（防漂移）、
架构级结晶结局为 `accepted`（不谎报 `published`）、技能级仍为 `published`、
未确认候选不产出任何发布类结局。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.evolution import (
    INTERNAL_PLUGIN_IDS,
    BenchmarkRegistry,
    Diagnoser,
    DiagnosisReport,
    Evaluator,
    EvolutionEngine,
    EvolutionError,
    EvolutionErrorCode,
    GenerationCandidate,
    PendingQueue,
    Proposer,
    Trace,
    Validator,
)
from core.permission import ApprovalRequest, ApprovalTicket, ApprovalWorkflow
from core.skills import SkillLibrary

_SRC = Path(__file__).resolve().parents[1] / "src" / "core"


def _module_trace(trace_id: str, module_id: str) -> Trace:
    """一条带模块归因的失败 trace（= `_to_traces` 模块通道的产出形状）。"""
    return Trace(
        trace_id=trace_id,
        task_type="module_health",
        action={"event": "loop_finished"},
        result={"failed": True},
        success=False,
        plugin_id=module_id,
    )


def _tool_trace(trace_id: str, tool: str) -> Trace:
    """一条工具通道的失败 trace（既有采集通道形状；`result` 非 None 才被采集）。"""
    return Trace(
        trace_id=trace_id,
        task_type="tool_use",
        action={"tool": tool},
        result={"ok": False},
        success=False,
        plugin_id=tool,
    )


class _RegisteredBaselines(BenchmarkRegistry):
    """测试替身：数据面上任意目标都视为已注册基线 0.5（判定面仍是真 `Evaluator`）。"""

    def baseline_of(self, _plugin_id: str) -> float | None:
        return 0.5


def _passing_evaluator() -> Evaluator:
    """过门评测器：基线可比（0.5）+ 留出分 0.9 ⇒ 真实地判 publish（0119 起无参裸桩不再恒通过）。"""
    return Evaluator(registry=_RegisteredBaselines(), score_fn=lambda _c: 0.9)


def _engine(
    *,
    library: SkillLibrary | None = None,
    proposer: Proposer | None = None,
    pending: PendingQueue | None = None,
) -> EvolutionEngine:
    return EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=proposer or Proposer(),
        validator=Validator(),
        evaluator=_passing_evaluator(),
        library=library,
        pending=pending,
    )


def _pending(engine: EvolutionEngine) -> GenerationCandidate:
    """跑一轮带模块归因的失败 → 过门候选（供 confirm/crystallize 消费）。"""
    outcome = engine.run_cycle([_module_trace("1", "loop.default")])
    assert outcome.candidate is not None
    return outcome.candidate


def _ticket(target: str) -> ApprovalTicket:
    workflow = ApprovalWorkflow()
    ticket = workflow.create(
        ApprovalRequest(
            op="evolution.publish",
            target=target,
            impact_summary="架构级候选结晶",
            rollback_plan="dissolve 回 L3",
            trace_id="evolution",
        )
    )
    workflow.approve(ticket, approver="alice")
    return ticket


# ---- 断裂 3：kind 由归因驱动，不再静态绑定 ----


def test_internal_module_target_yields_plugin_candidate() -> None:
    """归因到内部核心模块 ⇒ 架构级候选（而非被降格为技能级）。"""
    diagnosis = DiagnosisReport(target_plugin="loop.default", issue="预算耗尽")
    candidate = Proposer().propose(diagnosis)
    assert candidate.kind == "plugin"
    assert candidate.risk_level == "high"
    assert candidate.status == "pending"  # 人工门不放宽


def test_non_module_target_yields_skill_candidate() -> None:
    """归因到工具/记忆等非白名单目标 ⇒ 技能级候选（既有行为逐字不变）。"""
    for target in ("tools.file_read", "memory.retrieve"):
        candidate = Proposer().propose(DiagnosisReport(target_plugin=target, issue="x"))
        assert candidate.kind == "skill", target
        assert candidate.risk_level == "low", target


def test_explicit_kind_overrides_attribution() -> None:
    """显式 kind 优先于归因判定（既有 `Proposer(kind=…)` 调用语义不变）。"""
    diagnosis = DiagnosisReport(target_plugin="loop.default", issue="x")
    assert Proposer(kind="skill").propose(diagnosis).kind == "skill"
    assert Proposer(kind="plugin").propose(diagnosis).kind == "plugin"


def test_internal_plugin_ids_match_declared_plugin_ids() -> None:
    """归因白名单与仓内全部 `plugin_id = "..."` 声明逐元素一致（防漂移）。"""
    declared: set[str] = set()
    for path in _SRC.rglob("*.py"):
        declared.update(re.findall(r'plugin_id\s*=\s*"([^"]+)"', path.read_text("utf-8")))
    assert declared, "未扫到任何 plugin_id 声明（扫描口径失效）"
    assert set(INTERNAL_PLUGIN_IDS) == declared


# ---- 断裂 4：架构级结晶不谎报 published ----


def test_plugin_crystallize_reports_accepted_not_published() -> None:
    """模块归因 → 架构级候选 → 批准 → 结晶结局为 `accepted`（无产物发布）。"""
    engine = _engine()
    candidate = _pending(engine)
    assert candidate.target_plugin == "loop.default"
    assert candidate.kind == "plugin"
    assert candidate.risk_level == "high"
    engine.confirm(candidate, approval=_ticket(candidate.target_plugin))
    result = engine.crystallize(candidate)
    assert result.status == "accepted"
    assert result.skill_id is None  # 未落任何技能产物
    # 观察期仍开窗（判「批准之后是否回归」，与是否有产物无关）
    assert engine.observations.window("loop.default") is not None


def test_skill_crystallize_still_reports_published() -> None:
    """技能级候选确实写入技能库 ⇒ 结局仍为 `published`。"""
    library = SkillLibrary()
    engine = _engine(library=library)
    outcome = engine.run_cycle([_tool_trace("1", "tools.file_write")])
    candidate = outcome.candidate
    assert candidate is not None and candidate.kind == "skill"
    engine.confirm(candidate)
    result = engine.crystallize(candidate)
    assert result.status == "published"
    assert library.lookup(f"skills.evolution.{candidate.target_plugin}") is not None


def test_unconfirmed_candidate_yields_no_publish_outcome() -> None:
    """红线守护：未确认候选不得产出 `accepted` 亦不得产出 `published`。"""
    engine = _engine()
    candidate = _pending(engine)
    with pytest.raises(EvolutionError) as exc_info:
        engine.crystallize(candidate)
    assert exc_info.value.code is EvolutionErrorCode.CANDIDATE_PENDING
