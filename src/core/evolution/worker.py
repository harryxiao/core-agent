"""进化冷路径采集调度器（evolution）。

`EvolutionWorker` 消费 `Tracer` 已完成的 trace（热路径只登记 trace_id、不阻塞），
在 `EvolutionTrigger` 阈值命中或强制触发时，把 `TraceEvent` 适配为 evolution
`Trace` 并驱动 `EvolutionEngine.run_cycle`（诊断 → 提案 dry-run；验证门与结晶
见 Phase 15）。

对应接口：doc/03-interfaces/evolution-interface.md ｜ 规格 evolution/spec.md「经验采集」
"""

from __future__ import annotations

from typing import Any, cast

from core.observability import TraceEvent, Tracer

from .curriculum import CurriculumPlanner
from .engine import EvolutionEngine, EvolutionTrigger
from .models import EvolutionOutcome, Trace


class EvolutionWorker:
    """冷路径采集调度器：Tracer 轨迹 → evolution Trace → 进化引擎 dry-run。"""

    plugin_id = "evolution.worker"

    def __init__(
        self,
        tracer: Tracer,
        engine: EvolutionEngine,
        *,
        trigger: EvolutionTrigger | None = None,
        planner: CurriculumPlanner | None = None,
    ) -> None:
        self._tracer = tracer
        self._engine = engine
        self._trigger = trigger if trigger is not None else EvolutionTrigger()
        # 课程缺省**自动开课**（只读引擎公开面：观察期目标 + 待确认候选 ⇒ 零额外接线）
        self._planner = (
            planner
            if planner is not None
            else CurriculumPlanner(observations=engine.observations, pending=engine.pending)
        )
        self._completed: list[str] = []

    @property
    def engine(self) -> EvolutionEngine:
        """被驱动的进化引擎（操作面据此驱动人工确认队列）。"""
        return self._engine

    def on_trace_complete(self, trace_id: str) -> None:
        """热路径回调：登记一条已完成 trace（仅登记，不触发、不阻塞）。"""
        self._completed.append(trace_id)

    def maybe_run(self, *, force: bool = False, goal: str | None = None) -> EvolutionOutcome | None:
        """冷路径：阈值命中或强制时，replay 累积 trace → 课程定目标 → run_cycle（dry-run）。

        `goal`：显式目标（`evolve run --goal`）——**直接采用**、不参与归因竞争。
        """
        traces = self._collect()
        if not traces and not force:
            return None
        if not self._trigger.maybe_run(traces, force=force):
            return None
        outcome = self._engine.run_cycle(traces, goals=self._planner.plan(traces, explicit=goal))
        self._sample_observations(traces)
        self._completed.clear()
        return outcome

    def _sample_observations(self, traces: list[Trace]) -> None:
        """冷路径批次采样：对本批 trace 中**已开窗**的目标按 ``plugin_id`` 归因上报成功率。

        每个目标每轮至多上报一次样本；无归因 trace 的目标不采样（零样本）。批次成功率是
        线上代理指标，与留出评测分近似可比（见 evolution/spec「观察期回归自动溶解」）。
        """
        for target in self._engine.observations.targets():
            attributed = [trace for trace in traces if trace.plugin_id == target]
            if not attributed:
                continue
            self._engine.observe(target, sum(t.success for t in attributed) / len(attributed))

    def _collect(self) -> list[Trace]:
        traces: list[Trace] = []
        for trace_id in self._completed:
            traces.extend(self._to_traces(self._tracer.replay(trace_id)))
        return traces

    @staticmethod
    def _to_traces(events: list[TraceEvent]) -> list[Trace]:
        """把同 trace_id 的 TraceEvent 适配为 evolution Trace。

        仅 ``tool_call`` 事件产出 Trace（action/result 成对）；``plugin_id`` 从
        tool id 归因，供 Diagnoser 定位缺陷插件。
        """
        traces: list[Trace] = []
        for event in events:
            if event.kind != "tool_call":
                continue
            payload = event.payload
            tool = str(payload.get("tool", ""))
            result = payload.get("result")
            success = True
            if isinstance(result, dict):
                success = bool(cast(dict[str, Any], result).get("ok", True))
            traces.append(
                Trace(
                    trace_id=event.trace_id,
                    task_type="tool_use",
                    action={"tool": tool, "args": payload.get("args", {})},
                    result=result,
                    success=success,
                    plugin_id=tool or None,
                )
            )
        return traces
