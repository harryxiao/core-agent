"""对比诊断（evolution）。

归因缺陷到单一插件；无法归因 → `target_plugin=None`（系统级，engine 走 manual）。
归因线索来自 trace 的 `plugin_id` 与注入的插件质量信号（plugin-registry 元数据）。

对应接口：doc/03-interfaces/evolution-interface.md ｜ 规格 evolution/spec.md「对比诊断」
"""

from __future__ import annotations

from .models import DiagnosisReport, Trace, TraceRef


class Diagnoser:
    """对比诊断器：失败证据聚合归因到单一插件。"""

    plugin_id = "evolution.diagnoser"

    def __init__(self, plugin_signals: dict[str, float] | None = None) -> None:
        """`plugin_signals`: plugin_id → 失败强度信号（来自插件元数据，可空）。"""
        self._signals: dict[str, float] = dict(plugin_signals or {})

    def diagnose(self, traces: list[Trace]) -> DiagnosisReport:
        failed = [t for t in traces if not t.success]
        if not failed:
            return DiagnosisReport(target_plugin=None, issue="无失败证据", confidence=0.0)
        evidence = [TraceRef(trace_id=t.trace_id) for t in failed]
        scores: dict[str, float] = dict(self._signals)
        for t in failed:
            if t.plugin_id is not None:
                scores[t.plugin_id] = scores.get(t.plugin_id, 0.0) + 1.0
        if not scores:
            return DiagnosisReport(
                target_plugin=None,
                issue="无插件级归因线索",
                evidence=evidence,
                confidence=0.0,
            )
        top = max(scores, key=lambda p: scores[p])
        top_score = scores[top]
        rivals = [p for p, s in scores.items() if p != top and s == top_score]
        if rivals:
            return DiagnosisReport(
                target_plugin=None,
                issue="多插件并列，无法归因到单一插件",
                evidence=evidence,
                confidence=0.0,
            )
        return DiagnosisReport(
            target_plugin=top,
            issue=f"缺陷归因于插件 {top}",
            evidence=evidence,
            confidence=1.0,
        )
