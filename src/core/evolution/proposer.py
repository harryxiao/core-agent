"""模块级提案（evolution）。

`propose(diagnosis)` 产出世代化候选（不可变、带 delta 与 kind），**不自动发布**，
仅以 `status="pending"` 进入人工确认队列。

对应接口：doc/03-interfaces/evolution-interface.md ｜ 规格 evolution/spec.md「模块级提案」
"""

from __future__ import annotations

from typing import Literal

from .models import DiagnosisReport, GenerationCandidate


class Proposer:
    """模块级提案器：诊断 → 世代化候选。"""

    plugin_id = "evolution.proposer"

    def __init__(self, *, kind: Literal["skill", "plugin"] = "skill") -> None:
        self._kind: Literal["skill", "plugin"] = kind
        self._generation = 0

    def propose(self, diagnosis: DiagnosisReport) -> GenerationCandidate:
        assert diagnosis.target_plugin is not None  # engine 已拦截 None
        self._generation += 1
        return GenerationCandidate(
            generation=self._generation,
            target_plugin=diagnosis.target_plugin,
            delta={"issue": diagnosis.issue},
            kind=self._kind,
            status="pending",
            # 风险域随候选固化：架构级（plugin）必审，技能库级（skill）亦须人工确认
            risk_level="high" if self._kind == "plugin" else "low",
        )
