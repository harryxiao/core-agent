"""自动课程（目标生成与调度，change 0084 / 账本 E5）。

课程是冷路径的**目标选择层**：只吃**结构化信号**（本批失败计数 / 观察期目标 / 待确认候选），
**不读记忆自由文本、不调模型**。核心契约：产出的议程只作诊断**先验**，权重恒 < 1.0
⇒ **证据恒优先、先验只破并列**（降权亦然：只改并列顺序，不压证据）。
"""

from __future__ import annotations

from core.evolution import (
    CurriculumPlanner,
    EvolutionGoal,
    GenerationCandidate,
    ObservationRegistry,
    Trace,
)


def _trace(trace_id: str, *, success: bool, plugin_id: str | None = None) -> Trace:
    return Trace(
        trace_id=trace_id,
        task_type="t",
        action={"a": 1},
        result="ok",
        success=success,
        plugin_id=plugin_id,
    )


def _failures(plugin_id: str, count: int) -> list[Trace]:
    return [_trace(f"{plugin_id}-{i}", success=False, plugin_id=plugin_id) for i in range(count)]


def _candidate(target_plugin: str) -> GenerationCandidate:
    return GenerationCandidate(generation=1, target_plugin=target_plugin, delta={}, kind="skill")


def _ids(goals: list[EvolutionGoal]) -> list[str]:
    return [goal.plugin_id for goal in goals]


# ---- 定序：失败强度 ----


def test_plan_orders_by_failure_intensity() -> None:
    planner = CurriculumPlanner()
    goals = planner.plan([*_failures("A", 3), *_failures("B", 1)])
    assert _ids(goals) == ["A", "B"]
    assert "3" in goals[0].reason
    assert "1" in goals[1].reason


def test_plan_ignores_successes_and_unattributed_failures() -> None:
    """只有**有归因的失败**才算信号（成功与无归因失败不产生目标）。"""
    planner = CurriculumPlanner()
    traces = [
        _trace("ok", success=True, plugin_id="A"),
        _trace("orphan", success=False, plugin_id=None),
    ]
    assert planner.plan(traces) == []


# ---- 降权：已处理目标排在未处理之后 ----


def test_plan_deprioritizes_observed_target() -> None:
    """观察期中（已发布、正在观察）的目标降权 —— 刚迭代过的先别再迭代。"""
    registry = ObservationRegistry()
    registry.open("A", baseline=1.0)
    planner = CurriculumPlanner(observations=registry)
    goals = planner.plan([*_failures("A", 1), *_failures("B", 1)])
    assert _ids(goals) == ["B", "A"]
    assert "观察期" in goals[1].reason


def test_plan_deprioritizes_pending_candidate() -> None:
    """已有待确认候选（等人批）的目标降权 —— 不重复生成同一目标。"""
    planner = CurriculumPlanner(pending=lambda: [_candidate("A")])
    goals = planner.plan([*_failures("A", 1), *_failures("B", 1)])
    assert _ids(goals) == ["B", "A"]
    assert "待确认" in goals[1].reason


def test_plan_weights_stay_below_evidence() -> None:
    """先验权重恒 < 1.0（一条失败证据计 1.0）⇒ 先验只破并列、绝不压证据。"""
    registry = ObservationRegistry()
    registry.open("A", baseline=1.0)
    planner = CurriculumPlanner(observations=registry)
    goals = planner.plan([*_failures("A", 1), *_failures("B", 1)])
    assert all(0.0 < goal.score < 1.0 for goal in goals)
    assert goals[1].score < goals[0].score, "降权目标权重更低（并列时才起作用）"


# ---- 确定性与预算 ----


def test_plan_is_deterministic() -> None:
    traces = [*_failures("B", 1), *_failures("A", 1), *_failures("C", 1)]
    assert _ids(CurriculumPlanner().plan(traces)) == _ids(CurriculumPlanner().plan(traces))
    assert _ids(CurriculumPlanner().plan(traces)) == ["A", "B", "C"], "并列以 plugin_id 升序兜底"


def test_plan_respects_limit() -> None:
    planner = CurriculumPlanner()
    traces = [t for pid in "ABCDE" for t in _failures(pid, 1)]
    assert len(planner.plan(traces)) <= 3  # noqa: PLR2004 — 默认预算上界
    assert len(planner.plan(traces, limit=1)) == 1


# ---- 显式目标：指令，不参与竞争 ----


def test_plan_explicit_goal_is_directive() -> None:
    planner = CurriculumPlanner()
    goals = planner.plan([*_failures("B", 3)], explicit="A")
    assert _ids(goals) == ["A"], "显式目标不被证据改写"
    assert goals[0].directive is True
    assert goals[0].reason == "显式指定目标"


def test_plan_explicit_goal_without_any_evidence() -> None:
    """显式入口不依赖证据：没有失败 trace 也能聚焦指定目标（这是「可靠的探索入口」）。"""
    goals = CurriculumPlanner().plan([], explicit="A")
    assert _ids(goals) == ["A"]
