"""候选与结论台账（evolution）。

引擎产出的每条候选连同其**验证门报告**与**留出评测报告**记一条记录，整体落盘为 JSON 快照
并在启动时恢复。候选身份是构造即固化的 ``candidate_id``（**不是** ``id(obj)``）——这是跨进程
可用的前提：CLI 每条命令各起一份装配（`HarnessHost`），若结论检索绑在对象标识上，重启后
`crystallize` 会把一个本该发布的候选误判为「未过门 / 留出集退化」。

``pending()`` 给出**待确认**子集（``status == "pending"``）；已确认/已拒绝的记录留在台账中
充当最小审计痕迹（不额外建归档结构）。未注入路径（``path=None``）纯内存（零行为变化、不写盘）；
落盘缺失或损坏降级为空台账（不抛异常、不阻断启动）。

对应接口：doc/03-interfaces/evolution-interface.md §3.2
｜ 规格 evolution/spec.md「人工确认队列的持久化与操作面」
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from core.persistence import read_state, write_state

from .models import EvalReport, GateReport, GenerationCandidate


@dataclass
class PendingItem:
    """一条候选记录：候选 + 其门禁/评测结论（同生共死，不留半状态）。"""

    candidate: GenerationCandidate
    gate: GateReport | None = None
    eval: EvalReport | None = None


def _candidate_to_dict(candidate: GenerationCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "generation": candidate.generation,
        "target_plugin": candidate.target_plugin,
        "delta": candidate.delta,
        "kind": candidate.kind,
        "status": candidate.status,
        "risk_level": candidate.risk_level,
    }


def _candidate_from_dict(raw: dict[str, Any]) -> GenerationCandidate:
    kind: Literal["skill", "plugin"] = "plugin" if raw.get("kind") == "plugin" else "skill"
    risk: Literal["low", "high"] = "high" if raw.get("risk_level") == "high" else "low"
    return GenerationCandidate(
        candidate_id=str(raw.get("candidate_id") or ""),
        generation=int(raw.get("generation") or 0),
        target_plugin=str(raw.get("target_plugin") or ""),
        delta=dict(raw.get("delta") or {}),
        kind=kind,
        status=str(raw.get("status") or "pending"),
        risk_level=risk,
    )


def _gate_to_dict(gate: GateReport | None) -> dict[str, Any] | None:
    if gate is None:
        return None
    return {"passed": gate.passed, "review": gate.review, "test_results": gate.test_results}


def _gate_from_dict(raw: Any) -> GateReport | None:
    if not isinstance(raw, dict):
        return None
    data = cast("dict[str, Any]", raw)
    return GateReport(
        passed=bool(data.get("passed")),
        review=str(data.get("review") or ""),
        test_results=dict(data.get("test_results") or {}),
    )


def _eval_to_dict(report: EvalReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "passed": report.passed,
        "held_out_score": report.held_out_score,
        "baseline_score": report.baseline_score,
        "verdict": report.verdict,
    }


def _eval_from_dict(raw: Any) -> EvalReport | None:
    if not isinstance(raw, dict):
        return None
    data = cast("dict[str, Any]", raw)
    verdict = str(data.get("verdict") or "rollback")
    resolved: Literal["publish", "rollback", "freeze"] = "rollback"
    if verdict == "publish":
        resolved = "publish"
    elif verdict == "freeze":
        resolved = "freeze"
    return EvalReport(
        passed=bool(data.get("passed")),
        held_out_score=float(data.get("held_out_score") or 0.0),
        baseline_score=float(data.get("baseline_score") or 0.0),
        verdict=resolved,
    )


class PendingQueue:
    """候选与结论台账：落盘恢复 + 待确认子集 + 出队语义。"""

    def __init__(self, *, path: Path | None = None) -> None:
        self._path = path
        self._records: list[PendingItem] = []
        self._load()

    def record(
        self,
        candidate: GenerationCandidate,
        gate: GateReport | None = None,
        eval: EvalReport | None = None,  # noqa: A002 — 对齐领域词表（EvalReport）
    ) -> None:
        """登记一条候选（同 id 覆盖：门禁先行、评测补充），并落盘。"""
        self._records = [
            r for r in self._records if r.candidate.candidate_id != candidate.candidate_id
        ]
        self._records.append(PendingItem(candidate=candidate, gate=gate, eval=eval))
        self.flush()

    def flush(self) -> None:
        """把台账当前状态整体写盘（候选状态变更后调用）。"""
        self._persist()

    def records(self) -> list[PendingItem]:
        """台账快照（含已确认/已拒绝的痕迹）。"""
        return list(self._records)

    def pending(self) -> list[GenerationCandidate]:
        """待人工确认的候选（``status == "pending"``）。"""
        return [r.candidate for r in self._records if r.candidate.status == "pending"]

    def find(self, candidate_id: str) -> GenerationCandidate | None:
        """按稳定身份定位候选（不存在返回 ``None``）。"""
        for record in self._records:
            if record.candidate.candidate_id == candidate_id:
                return record.candidate
        return None

    def gate_of(self, candidate_id: str) -> GateReport | None:
        for record in self._records:
            if record.candidate.candidate_id == candidate_id:
                return record.gate
        return None

    def eval_of(self, candidate_id: str) -> EvalReport | None:
        for record in self._records:
            if record.candidate.candidate_id == candidate_id:
                return record.eval
        return None

    def _load(self) -> None:
        raw = read_state(self._path)
        if not isinstance(raw, dict):
            return
        data = cast("dict[str, Any]", raw)
        records = data.get("records")
        if not isinstance(records, list):
            return
        for entry in cast("list[Any]", records):
            if not isinstance(entry, dict):
                continue
            record = cast("dict[str, Any]", entry)
            if not record.get("candidate_id"):
                continue
            self._records.append(
                PendingItem(
                    candidate=_candidate_from_dict(record),
                    gate=_gate_from_dict(record.get("gate")),
                    eval=_eval_from_dict(record.get("eval")),
                )
            )

    def _persist(self) -> None:
        write_state(
            self._path,
            {
                "records": [
                    {
                        **_candidate_to_dict(r.candidate),
                        "gate": _gate_to_dict(r.gate),
                        "eval": _eval_to_dict(r.eval),
                    }
                    for r in self._records
                ]
            },
        )


__all__ = ["PendingItem", "PendingQueue"]
