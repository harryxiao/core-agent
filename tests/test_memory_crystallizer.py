"""结晶 / 溶解钩子的可用性单测（change 0305 / ADR-0295 / 台账 E241）。

对应规格：
  * `doc/openspec/specs/memory/spec.md`「技能结晶与溶解钩子的可用性」
  * `doc/openspec/specs/evolution/spec.md`「架构级候选的结晶产物随结局返回」

三面：复用门（3 次成功）/ 显式 force 豁免 / 溶解教训可入库 / 引擎产物不再丢弃。
"""

from __future__ import annotations

from core.evolution import (
    BenchmarkRegistry,
    Diagnoser,
    Evaluator,
    EvolutionEngine,
    Proposer,
    Trace,
    Validator,
)
from core.memory import Crystallizer, MemoryEntry, MemoryStore
from core.permission import ApprovalRequest, ApprovalTicket, ApprovalWorkflow

# 阈值 3 逐字对齐 SDD「技能晋级至少 3 次成功或 1 次显式用户要求」。
_THRESHOLD = 3
_BELOW_THRESHOLD = _THRESHOLD - 1


def _skill_entry(reuse_count: int) -> MemoryEntry:
    return MemoryEntry(
        id="skill.deploy",
        layer="L3",
        content="流程：先跑测试再发布",
        tags=["skill"],
        source="evolution",
        trace_id="evolution",
        reuse_count=reuse_count,
    )


# ---- 复用门 ----


def test_below_threshold_yields_no_candidate() -> None:
    """复用 2 次（<3）⇒ 不产出插件候选。"""
    assert Crystallizer().crystallize(_skill_entry(_BELOW_THRESHOLD)) is None


def test_threshold_yields_candidate() -> None:
    """复用 3 次 ⇒ 产出候选，来源指向技能条目。"""
    candidate = Crystallizer().crystallize(_skill_entry(_THRESHOLD))

    assert candidate is not None
    assert candidate.plugin_id == "skill.skill.deploy"
    assert candidate.generation == 1
    assert candidate.source_entry_id == "skill.deploy"
    assert candidate.schema["content"] == "流程：先跑测试再发布"


def test_force_bypasses_threshold() -> None:
    """显式要求 / 已获人工批准 ⇒ 复用 0 次也可结晶。"""
    candidate = Crystallizer().crystallize(_skill_entry(0), force=True)

    assert candidate is not None
    assert candidate.source_entry_id == "skill.deploy"


# ---- 溶解教训 ----


def test_dissolve_lesson_is_writable() -> None:
    """溶解产物带非空 trace_id ⇒ 可被 MemoryStore 接受并落盘。"""
    lesson = Crystallizer().dissolve("tools.file_write")
    store = MemoryStore()

    assert lesson.trace_id
    written = store.write("L3", lesson)
    assert written == lesson.id
    assert lesson.id in {str(entry.id) for entry in store.audit()}


# ---- 引擎不再丢弃产物 ----


class _RegisteredBaselines(BenchmarkRegistry):
    """测试替身：数据面上任意目标都有可比基线（0.5）。"""

    def baseline_of(self, _plugin_id: str) -> float | None:
        return 0.5


def _engine(*, crystallizer: Crystallizer | None) -> EvolutionEngine:
    return EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=Proposer(kind="plugin"),
        validator=Validator(
            review=lambda _c: True,
            tests=lambda _c: {"lint": True, "test": True},
        ),
        evaluator=Evaluator(registry=_RegisteredBaselines(), score_fn=lambda _c: 0.9),
        memory_crystallizer=crystallizer,
    )


def _confirmed_candidate(engine: EvolutionEngine):
    outcome = engine.run_cycle(
        [
            Trace(
                trace_id="1",
                task_type="t",
                action={"a": 1},
                result="ok",
                success=False,
                plugin_id="memory.retrieve",
            )
        ]
    )
    assert outcome.candidate is not None
    engine.confirm(outcome.candidate, approval=_ticket(outcome.candidate.target_plugin))
    return outcome.candidate


def _ticket(target: str) -> ApprovalTicket:
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
    workflow.approve(ticket, approver="alice")
    return ticket


def test_plugin_candidate_artifact_is_returned() -> None:
    """装配钩子 ⇒ 产物随 accepted 结局返回（合成条目复用 0 次，靠 force 豁免）。"""
    engine = _engine(crystallizer=Crystallizer())
    candidate = _confirmed_candidate(engine)

    result = engine.crystallize(candidate)

    assert result.status == "accepted"
    assert result.artifact is not None
    assert result.artifact.source_entry_id == f"evolution.candidate.{candidate.generation}"


def test_plugin_candidate_without_crystallizer_has_no_artifact() -> None:
    """未装配钩子 ⇒ artifact 为 None，结局仍 accepted。"""
    engine = _engine(crystallizer=None)
    candidate = _confirmed_candidate(engine)

    result = engine.crystallize(candidate)

    assert result.status == "accepted"
    assert result.artifact is None
