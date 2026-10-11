"""任务级 SOP 过程输入 —— 组合根接缝（change 0197 / ADR-0187 / 台账 E134）。

覆盖 runtime 侧两件纯件：`_steps_lookup`（零效应回读子任务步序）与 `compose_task_steps`
（按 `plan.order` 聚合）。任务级 `SopExtractor` 的 `namespace` 行为由 `test_skills.py` 承载；
端到端「任务 DONE → SOP 入库」由 change 0199 承载。
"""

from __future__ import annotations

from core.memory import FileBackend, MemoryEntry
from core.orchestration import Plan, Subtask
from core.orchestration.scheduler import SubtaskOutcome
from core.runtime import (
    _MAX_TASK_STEP_CHARS,
    _MAX_TASK_STEPS_CHARS,
    _steps_lookup,
    compose_task_steps,
)


def _step_entry(entry_id: str, content: str) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=["loop", "steps"],
        source="loop",
        trace_id=entry_id.removeprefix("loop.steps."),
    )


def test_steps_lookup_reads_loop_steps_by_id() -> None:
    backend = FileBackend()
    backend.put(_step_entry("loop.steps.T1", "tools.echo → ok\ntools.write → ok"))
    backend.put(_step_entry("loop.steps.T2", "tools.read → 42"))

    lookup = _steps_lookup(backend)

    assert lookup("T1") == ["tools.echo → ok", "tools.write → ok"]
    assert lookup("T2") == ["tools.read → 42"]
    assert lookup("未沉淀") == [], "无条目 ⇒ 空列表（不伪造）"


def test_steps_lookup_is_zero_effect() -> None:
    """回读走 `search`（不经 `read`）⇒ 不强化 `reuse_count`、不落盘（守 P2）。"""
    backend = FileBackend()
    backend.put(_step_entry("loop.steps.T1", "a\nb"))
    lookup = _steps_lookup(backend)

    before = backend.get("L2", "loop.steps.T1")
    assert before is not None and before.reuse_count == 0

    assert lookup("T1") == ["a", "b"]

    after = backend.get("L2", "loop.steps.T1")
    assert after is not None and after.reuse_count == 0, "查找不强化 reuse_count（零效应）"


def test_compose_task_steps_follows_plan_order() -> None:
    """按 `plan.order` 聚合子任务步序；乱序 outcomes 不改变输出顺序；缺失 trace 跳过不炸。"""
    plan = Plan(
        goal="季度汇总",
        subtasks=[
            Subtask(id="s1", goal="取数", acceptance=""),
            Subtask(id="s2", goal="汇总", acceptance=""),
            Subtask(id="s3", goal="发布", acceptance=""),
        ],
        order=["s1", "s2", "s3"],
    )
    outcomes = [
        SubtaskOutcome(subtask_id="s2", ok=True, trace_id="T2"),
        SubtaskOutcome(subtask_id="s1", ok=True, trace_id="T1"),
        SubtaskOutcome(subtask_id="s3", ok=True, trace_id=""),  # 无 trace ⇒ 跳过
    ]
    steps = {"T1": ["tools.fetch → ok"], "T2": ["tools.sum → ok"]}

    def lookup(tid: str) -> list[str]:
        return steps.get(tid, [])

    composed = compose_task_steps(plan, outcomes, lookup)

    heads = [line.split("：", 1)[0] for line in composed]
    assert heads == ["子任务 取数", "子任务 汇总"], "按 plan.order 聚合；无 trace 者跳过不炸"
    assert "tools.fetch → ok" in composed[0]
    assert "tools.sum → ok" in composed[1]


def test_compose_task_steps_bounded() -> None:
    """总长有上界（token 有界）：单行截断至 `_MAX_TASK_STEP_CHARS`，聚合体超界即**提前收敛**。"""
    subtask_ids = [f"s{i}" for i in range(20)]
    plan = Plan(
        goal="g",
        subtasks=[Subtask(id=sid, goal="t", acceptance="") for sid in subtask_ids],
        order=subtask_ids,
    )
    outcomes = [SubtaskOutcome(subtask_id=sid, ok=True, trace_id=sid) for sid in subtask_ids]

    def lookup(_tid: str) -> list[str]:
        return ["x" * 5000]  # 单行远超单行上界

    composed = compose_task_steps(plan, outcomes, lookup)

    total = sum(len(line) for line in composed)
    assert total <= _MAX_TASK_STEPS_CHARS, "聚合结果有上界（token 有界）"
    assert len(composed) < len(subtask_ids), "超界即提前收敛，不聚满全部子任务"
    longest = max(len(line) for line in composed)
    assert longest <= _MAX_TASK_STEP_CHARS, "单行截断至单行上界"
