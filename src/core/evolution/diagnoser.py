"""对比诊断（evolution）。

归因缺陷到单一插件；无法归因 → `target_plugin=None`（系统级，engine 走 manual）。
归因线索来自 trace 的 `plugin_id` 与注入的插件质量信号（plugin-registry 元数据）。

**目标先验**（`diagnose(prior=…)`，change `0084`）来自课程议程：权重恒 < 1.0 ⇒ **证据恒优先**，
先验的**唯一**效果是解并列（无先验时并列仍转人工）。

对应接口：doc/03-interfaces/evolution-interface.md ｜ 规格 evolution/spec.md「对比诊断」
"""

from __future__ import annotations

from collections.abc import Callable

from .models import DiagnosisReport, Trace, TraceRef

# 失败摘要并入的**界**（change 0188 / ADR-0179）：单条截断 + 总数封顶 —— 诊断报告不得因
# 摘要面而无界增长。截断保留**先到**（最早）的失败证据，比后到更可预期。
_MAX_NOTE_CHARS = 400
_MAX_FAILURE_NOTES = 3


class Diagnoser:
    """对比诊断器：失败证据聚合归因到单一插件。"""

    plugin_id = "evolution.diagnoser"

    def __init__(
        self,
        plugin_signals: dict[str, float] | None = None,
        failure_lookup: Callable[[str], str | None] | None = None,
    ) -> None:
        """`plugin_signals`: plugin_id → 失败强度信号（来自插件元数据，可空）。

        `failure_lookup`（change 0188 / ADR-0179）：**可选**的失败摘要查询接缝
        （`trace_id → 已沉淀摘要 | None`），**依赖倒置**注入 —— 本单元不 import memory。
        缺省 `None`（未接线）⇒ 报告 `failure_notes` 恒空、诊断与既往**逐字一致**。
        """
        self._signals: dict[str, float] = dict(plugin_signals or {})
        self._failure_lookup = failure_lookup

    def _with_failure_notes(self, report: DiagnosisReport, failed: list[Trace]) -> DiagnosisReport:
        """把已沉淀的轮级失败摘要并入报告（**有界**；未接线 / 查询抛错 ⇒ 原样返回）。

        查询抛错 ⇒ **降级**（跳过该 trace），归因判定不受牵连（与 embedder 降级同纪律）。
        """
        lookup = self._failure_lookup
        if lookup is None:
            return report
        for trace in failed:
            if len(report.failure_notes) >= _MAX_FAILURE_NOTES:
                break
            try:
                note = lookup(trace.trace_id)
            except Exception:  # noqa: BLE001 — 查询失败降级：不牵连归因判定
                continue
            if note and note.strip():
                report.failure_notes.append(note[:_MAX_NOTE_CHARS])
        return report

    def diagnose(
        self, traces: list[Trace], *, prior: dict[str, float] | None = None
    ) -> DiagnosisReport:
        """归因到单一插件。`prior`：课程议程的先验权重（< 1.0 ⇒ 只破并列，不压证据）。"""
        failed = [t for t in traces if not t.success]
        if not failed:
            return self._with_failure_notes(
                DiagnosisReport(target_plugin=None, issue="无失败证据", confidence=0.0), failed
            )
        evidence = [TraceRef(trace_id=t.trace_id) for t in failed]
        scores: dict[str, float] = dict(self._signals)
        for plugin_id, weight in (prior or {}).items():
            scores[plugin_id] = scores.get(plugin_id, 0.0) + weight
        for t in failed:
            if t.plugin_id is not None:
                scores[t.plugin_id] = scores.get(t.plugin_id, 0.0) + 1.0
        if not scores:
            return self._with_failure_notes(
                DiagnosisReport(
                    target_plugin=None,
                    issue="无插件级归因线索",
                    evidence=evidence,
                    confidence=0.0,
                ),
                failed,
            )
        top = max(scores, key=lambda p: scores[p])
        top_score = scores[top]
        rivals = [p for p, s in scores.items() if p != top and s == top_score]
        if rivals:
            return self._with_failure_notes(
                DiagnosisReport(
                    target_plugin=None,
                    issue="多插件并列，无法归因到单一插件",
                    evidence=evidence,
                    confidence=0.0,
                ),
                failed,
            )
        return self._with_failure_notes(
            DiagnosisReport(
                target_plugin=top,
                issue=f"缺陷归因于插件 {top}",
                evidence=evidence,
                confidence=1.0,
            ),
            failed,
        )
