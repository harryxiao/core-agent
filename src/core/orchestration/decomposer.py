"""子任务拆解（orchestration）。

大目标 → 分步子任务 DAG（含验收标准与依赖），按依赖拓扑序执行，并划分
波次（wave：同一波次内无相互依赖）；依赖成环时报 ``DEADLOOP_DETECTED``。
默认拆解为单子任务（离线无模型可用），可注入 planner 换 LLM 拆解。

对应接口：doc/03-interfaces/orchestration-interface.md §2
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from .errors import OrchestrationError, OrchestrationErrorCode
from .models import Plan, Subtask, VerifyResult

Planner = Callable[[str], list[Subtask]]


class SubtaskDecomposer:
    """子任务拆解器：拆解目标为 Plan + 校验子任务结果。"""

    def __init__(self, planner: Planner | None = None) -> None:
        self._planner = planner

    def decompose(self, goal: str, success_criteria: list[str] | None = None) -> Plan:
        """大目标 → 分步 Todo（含验收标准与依赖 DAG），划分拓扑序与波次。"""
        subtasks = (
            self._planner(goal)
            if self._planner is not None
            else [Subtask(id="1", goal=goal, acceptance="")]
        )
        order = self._topological_order(subtasks)
        if len(order) < len(subtasks):
            raise OrchestrationError(
                OrchestrationErrorCode.DEADLOOP_DETECTED, "子任务依赖成环，无法拓扑排序"
            )
        waves = self._build_waves(subtasks, order)
        return Plan(
            subtasks=subtasks,
            goal=goal,
            order=order,
            success_criteria=success_criteria or [],
            waves=waves,
        )

    def verify(self, subtask: Subtask, result: Any) -> VerifyResult:
        """用验收标准校验子任务结果；通过才推进（离线简单判定：结果非空即通过）。"""
        text = str(result or "").strip()
        if not text:
            return VerifyResult(passed=False, reason=f"子任务 {subtask.id} 结果为空")
        return VerifyResult(passed=True, reason="结果非空，验收通过")

    def _topological_order(self, subtasks: list[Subtask]) -> list[str]:
        """Kahn 拓扑排序；存在环时返回顺序不完整（长度 < 子任务数）。"""
        ids = {s.id for s in subtasks}
        indegree = {s.id: 0 for s in subtasks}
        dependents: dict[str, list[str]] = {s.id: [] for s in subtasks}
        for s in subtasks:
            for dep in s.depends_on:
                if dep in ids:
                    indegree[s.id] += 1
                    dependents[dep].append(s.id)
        ready = deque(s.id for s in subtasks if indegree[s.id] == 0)
        order: list[str] = []
        while ready:
            node = ready.popleft()
            order.append(node)
            for nxt in dependents[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)
        return order

    def _build_waves(self, subtasks: list[Subtask], order: list[str]) -> list[list[str]]:
        """按依赖层级划分波次：层号 = 1 + 依赖层号最大值，同层无相互依赖。"""
        by_id = {s.id: s for s in subtasks}
        level: dict[str, int] = {}
        for sid in order:
            deps = by_id[sid].depends_on
            level[sid] = 1 + max((level[d] for d in deps if d in level), default=0)
        waves: dict[int, list[str]] = {}
        for sid in order:
            waves.setdefault(level[sid], []).append(sid)
        return [waves[k] for k in sorted(waves)]
