"""0234 · 未过门候选教训写回 L2 全文 + L3 短指针（ADR 级实现对齐）。"""

from __future__ import annotations

from core.evolution import (
    Diagnoser,
    Evaluator,
    EvolutionEngine,
    Proposer,
    Trace,
    Validator,
)
from core.evolution.models import DiagnosisReport, GenerationCandidate
from core.memory import FileBackend

_MAX_ISSUE_CHARS = 400  # 与 engine 同口径字面量（测试侧自持，不碰私有符号）


def _trace(trace_id: str = "1", *, plugin_id: str = "memory.retrieve") -> Trace:
    return Trace(
        trace_id=trace_id,
        task_type="t",
        action={"a": 1},
        result="err",
        success=False,
        plugin_id=plugin_id,
    )


class _LongIssueProposer(Proposer):
    """提案后把 issue 撑超上界，用于截断断言。"""

    def propose(self, diagnosis: DiagnosisReport) -> GenerationCandidate:
        candidate = super().propose(diagnosis)
        candidate.delta["issue"] = "甲" * (_MAX_ISSUE_CHARS + 80)
        return candidate


def _rejecting_engine(
    *, memory: object | None, proposer: Proposer | None = None
) -> EvolutionEngine:
    return EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=proposer if proposer is not None else Proposer(),
        validator=Validator(review=lambda _c: False, tests=lambda _c: {"lint": True}),
        evaluator=Evaluator(),
        memory=memory,  # type: ignore[arg-type]
    )


def test_rejected_writes_bounded_l2_lesson() -> None:
    """2.1 L2：id/层正确；含 target/issue/review；超长 issue 截到 400。"""
    backend = FileBackend()
    engine = _rejecting_engine(memory=backend, proposer=_LongIssueProposer())
    outcome = engine.run_cycle([_trace()])
    assert outcome.status == "rejected" and outcome.candidate is not None
    cid = outcome.candidate.candidate_id
    entry = backend.get("L2", f"evolution.gate_rejected.{cid}")
    assert entry is not None
    assert entry.layer == "L2"
    assert "memory.retrieve" in entry.content
    assert "review=" in entry.content
    assert "issue=" in entry.content
    after = entry.content.split("issue=", 1)[1]
    issue_part = after.split(" review=", 1)[0]
    assert len(issue_part) == _MAX_ISSUE_CHARS


def test_rejected_writes_l3_pointer_not_full_copy() -> None:
    """2.2 L3：短指针含 ref=；不等于 L2 全文；不含完整超长 issue。"""
    backend = FileBackend()
    engine = _rejecting_engine(memory=backend, proposer=_LongIssueProposer())
    outcome = engine.run_cycle([_trace()])
    assert outcome.status == "rejected" and outcome.candidate is not None
    cid = outcome.candidate.candidate_id
    l2_id = f"evolution.gate_rejected.{cid}"
    l2 = backend.get("L2", l2_id)
    l3 = backend.get("L3", f"evolution.gate_rejected.l3.{cid}")
    assert l2 is not None and l3 is not None
    assert f"ref={l2_id}" in l3.content
    assert l3.content != l2.content
    assert "issue=" not in l3.content
    assert "甲" * 50 not in l3.content


def test_rejected_skips_when_memory_missing() -> None:
    """2.3 未注入 memory ⇒ 零写、不抛、仍 rejected。"""
    engine = _rejecting_engine(memory=None)
    outcome = engine.run_cycle([_trace()])
    assert outcome.status == "rejected"


def test_gate_rejected_coexists_with_human_reject() -> None:
    """2.4 门禁 gate_rejected* 与人工 evolution.rejected.* 并存。"""
    backend = FileBackend()
    engine = _rejecting_engine(memory=backend)
    outcome = engine.run_cycle([_trace()])
    assert outcome.candidate is not None
    cid = outcome.candidate.candidate_id
    engine.reject(outcome.candidate, reason="人工否决")
    assert backend.get("L2", f"evolution.gate_rejected.{cid}") is not None
    assert backend.get("L3", f"evolution.gate_rejected.l3.{cid}") is not None
    human = backend.get("L2", f"evolution.rejected.{cid}")
    assert human is not None
    assert "人工否决" in human.content


def test_other_branches_do_not_write_gate_rejected() -> None:
    """2.5 no_evidence / frozen 等不写 gate_rejected*。"""
    backend = FileBackend()
    engine = EvolutionEngine(
        diagnoser=Diagnoser(),
        proposer=Proposer(),
        validator=Validator(review=lambda _c: True, tests=lambda _c: {"lint": True, "test": True}),
        evaluator=Evaluator(),
        memory=backend,
    )
    assert engine.run_cycle([]).status == "no_evidence"
    assert backend.search("gate_rejected") == []

    outcome = engine.run_cycle([_trace()])
    assert outcome.status == "frozen"
    assert all("gate_rejected" not in e.id for e in backend.search(""))
