"""模块级提案（evolution）。

`propose(diagnosis)` 产出世代化候选（不可变、带 delta 与 kind），**不自动发布**，
仅以 `status="pending"` 进入人工确认队列。候选 `kind` 由**诊断归因**驱动
（归因到内部核心模块 ⇒ `plugin`，否则 ⇒ `skill`），构造参数仅作**显式覆盖**。

对应接口：doc/03-interfaces/evolution-interface.md ｜ 规格 evolution/spec.md「模块级提案」
"""

from __future__ import annotations

from typing import Literal

from .models import DiagnosisReport, GenerationCandidate
from .plugin_ids import INTERNAL_PLUGIN_IDS


class Proposer:
    """模块级提案器：诊断 → 世代化候选（kind 由归因驱动，可显式覆盖）。"""

    plugin_id = "evolution.proposer"

    def __init__(self, *, kind: Literal["skill", "plugin"] | None = None) -> None:
        """``kind`` 是**显式覆盖**：``None``（缺省）表示按诊断归因判定。"""
        self._kind: Literal["skill", "plugin"] | None = kind
        self._generation = 0

    def propose(self, diagnosis: DiagnosisReport) -> GenerationCandidate:
        assert diagnosis.target_plugin is not None  # engine 已拦截 None
        # 归因驱动：归因到内部核心模块 ⇒ 架构级；显式覆盖优先
        kind: Literal["skill", "plugin"] = self._kind or (
            "plugin" if diagnosis.target_plugin in INTERNAL_PLUGIN_IDS else "skill"
        )
        self._generation += 1
        return GenerationCandidate(
            generation=self._generation,
            target_plugin=diagnosis.target_plugin,
            delta={"issue": diagnosis.issue},
            kind=kind,
            status="pending",
            # 风险域随候选固化：架构级（plugin）必审，技能库级（skill）亦须人工确认
            risk_level="high" if kind == "plugin" else "low",
        )
