"""难易度感知的同波次调度策略（change 0123 / phase-29 change C：E50）。

规格「难易度感知的调度策略」要求：`Subtask.difficulty` 三档（缺省 `medium`，
集合外**归一**而非抛错）；
同波次调度策略**可配置** —— `off`（缺省）维持依赖拓扑并发（与引入前**逐字一致**），`difficulty` 时
**含 `hard` 的波次串行**、否则并发；依赖拓扑仍是硬约束；`max_concurrency` 由组合根注入。

本文件证明：缺省不回归既有并发 / `difficulty` 只**收窄**不放大 / hard 与 easy 分处不同波次时只有含
hard 的波次串行 / 非法难易度归一 / 计划持久化往返不丢字段（旧检查点缺键回落）/ 构造器策略取值非法
报 `INVALID_DISPATCH_POLICY`。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest

from core.loop import Action, DefaultLoop, LoopEvent
from core.orchestration import (
    AgentProfile,
    LLMSubtaskPlanner,
    MultiAgentRouter,
    OrchestrationError,
    OrchestrationErrorCode,
    Plan,
    StateMachine,
    Subtask,
    SubtaskDecomposer,
    TaskScheduler,
    plan_from_dict,
    plan_to_dict,
)
from core.orchestration.models import normalize_difficulty


class _WaveTracker:
    """记录入/出时间线（asyncio 单线程，无需加锁）⇒ 可判「是否重叠」。"""

    def __init__(self) -> None:
        self.timeline: list[str] = []
        self.active = 0
        self.peak = 0

    def enter(self, name: str) -> None:
        self.timeline.append(f"+{name}")
        self.active += 1
        self.peak = max(self.peak, self.active)

    def exit(self, name: str) -> None:
        self.timeline.append(f"-{name}")
        self.active -= 1

    def slice(self, names: list[str]) -> list[str]:
        """取涉及给定子任务的时间线片段，统一为 `+名` / `-名`（按波次断言用）。

        前缀匹配入参：有依赖的子任务入参含「前置子任务结果」交接段（非裸 goal）。
        """
        out: list[str] = []
        for mark in self.timeline:
            matched = next((n for n in names if mark[1:].startswith(n)), None)
            if matched is not None:
                out.append(f"{mark[0]}{matched}")
        return out


class _TrackingLoop(DefaultLoop):
    """带并发窗口的测试循环（编排层经流式入口执行子任务）。"""

    def __init__(self, tracker: _WaveTracker) -> None:
        super().__init__(planner=lambda ctx: Action(args={"reply": "ok"}))
        self._tracker = tracker

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        self._tracker.enter(user_input)
        await asyncio.sleep(0.01)  # 拉开窗口：并发时入/出必然交错
        self._tracker.exit(user_input)
        async for event in super().astream(user_input, session_id=session_id):
            yield event


def _scheduler(
    subtasks: list[Subtask],
    tracker: _WaveTracker,
    *,
    policy: str = "off",
    max_concurrency: int = 4,
) -> TaskScheduler:
    profile = AgentProfile(agent_id="a", capabilities=["t"], loop=_TrackingLoop(tracker))
    return TaskScheduler(
        decomposer=SubtaskDecomposer(planner=lambda goal: subtasks),
        router=MultiAgentRouter(agents=[profile]),
        state_machine=StateMachine(),
        max_concurrency=max_concurrency,
        difficulty_policy=policy,
    )


# ---- 调度策略：缺省不回归 ----


def test_default_policy_keeps_topology_concurrency() -> None:
    """缺省 `off` ⇒ 同波次并发（峰值受上限约束），与引入策略前逐字一致。"""
    tracker = _WaveTracker()
    subtasks = [Subtask(id=str(i), goal=f"t-{i}", acceptance="") for i in range(4)]
    asyncio.run(_scheduler(subtasks, tracker, max_concurrency=2).run("task", "goal"))
    assert tracker.peak == 2  # noqa: PLR2004 — 即 max_concurrency


def test_difficulty_policy_serializes_wave_containing_hard() -> None:
    """`difficulty` 策略：波次含 `hard` ⇒ 整波串行（峰值 1），按优先级降序逐个。"""
    tracker = _WaveTracker()
    subtasks = [
        Subtask(id="e", goal="t-e", acceptance="", difficulty="easy", priority=0),
        Subtask(id="h", goal="t-h", acceptance="", difficulty="hard", priority=10),
        Subtask(id="m", goal="t-m", acceptance="", difficulty="medium", priority=5),
    ]
    asyncio.run(
        _scheduler(subtasks, tracker, policy="difficulty", max_concurrency=4).run("task", "goal")
    )
    assert tracker.peak == 1
    # 交接 prompt 追加原始目标（change 0247），时序按首行判定
    assert [m.split("\n\n")[0] for m in tracker.timeline] == [
        "+t-h",
        "-t-h",
        "+t-m",
        "-t-m",
        "+t-e",
        "-t-e",
    ]


def test_difficulty_policy_keeps_concurrency_without_hard() -> None:
    """`difficulty` 策略：波次全为 easy/medium ⇒ 维持并发。"""
    tracker = _WaveTracker()
    subtasks = [
        Subtask(id="e", goal="t-e", acceptance="", difficulty="easy"),
        Subtask(id="m", goal="t-m", acceptance="", difficulty="medium"),
    ]
    asyncio.run(
        _scheduler(subtasks, tracker, policy="difficulty", max_concurrency=2).run("task", "goal")
    )
    assert tracker.peak == 2  # noqa: PLR2004 — 即 max_concurrency


def test_only_hard_wave_is_serialized_across_waves() -> None:
    """跨波次：只有含 `hard` 的波次串行，另一波次仍并发（策略非全局降级）。"""
    tracker = _WaveTracker()
    subtasks = [
        Subtask(id="e1", goal="t-e1", acceptance="", difficulty="easy", priority=20),
        Subtask(id="e2", goal="t-e2", acceptance="", difficulty="easy", priority=10),
        Subtask(
            id="h1",
            goal="t-h1",
            acceptance="",
            depends_on=["e1"],
            difficulty="hard",
            priority=20,
        ),
        Subtask(
            id="h2",
            goal="t-h2",
            acceptance="",
            depends_on=["e1"],
            difficulty="hard",
            priority=10,
        ),
    ]
    asyncio.run(
        _scheduler(subtasks, tracker, policy="difficulty", max_concurrency=2).run("task", "goal")
    )
    # 波次 1（e1/e2 无依赖）并发 ⇒ 两者先入（重叠窗口存在）；
    # 波次 2（h1/h2 皆 hard）串行 ⇒ 严格不重叠
    assert tracker.peak == 2  # noqa: PLR2004 — 并发能力未被全局回收
    assert tracker.slice(["t-e1", "t-e2"])[:2] == ["+t-e1", "+t-e2"]
    assert tracker.slice(["t-h1", "t-h2"]) == ["+t-h1", "-t-h1", "+t-h2", "-t-h2"]


# ---- 难易度字段：缺省 / 归一 / 往返 ----


def test_difficulty_defaults_to_medium() -> None:
    assert Subtask(id="1", goal="g", acceptance="").difficulty == "medium"


@pytest.mark.parametrize("raw", ["urgent", "1", "", "very hard", "HARD!", "中"])
def test_illegal_difficulty_normalized_to_medium(raw: str) -> None:
    """归一后仍在集合外 ⇒ 取 `medium`（弱信号不阻断拆解）。"""
    assert Subtask(id="1", goal="g", acceptance="", difficulty=raw).difficulty == "medium"


@pytest.mark.parametrize("raw", [1, None, 1.5, ["hard"], {"level": "hard"}])
def test_non_string_difficulty_normalized_to_medium(raw: object) -> None:
    """JSON 弱类型（int / null / list / dict）⇒ 归一为 `medium`，不抛裸异常。"""
    assert normalize_difficulty(raw) == "medium"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("HARD", "hard"), (" hard ", "hard"), ("Easy", "easy"), (" Medium", "medium")],
)
def test_difficulty_case_and_whitespace_normalized(raw: str, expected: str) -> None:
    """大小写/空白变体 ⇒ 归一为对应档位，而非因字面不等降级为 `medium`。"""
    assert Subtask(id="1", goal="g", acceptance="", difficulty=raw).difficulty == expected


@pytest.mark.parametrize("level", ["easy", "medium", "hard"])
def test_legal_difficulty_preserved(level: str) -> None:
    assert Subtask(id="1", goal="g", acceptance="", difficulty=level).difficulty == level


def test_plan_roundtrip_preserves_difficulty() -> None:
    plan = Plan(
        subtasks=[Subtask(id="1", goal="g", acceptance="", difficulty="hard")],
        goal="g",
    )
    assert plan_from_dict(plan_to_dict(plan)).subtasks[0].difficulty == "hard"


def test_plan_from_dict_missing_difficulty_falls_back() -> None:
    """旧检查点无该键 ⇒ 回落 `medium`（向后兼容，不丢子任务、不抛）。"""
    legacy = {"goal": "g", "subtasks": [{"id": "1", "goal": "g", "acceptance": ""}]}
    assert plan_from_dict(legacy).subtasks[0].difficulty == "medium"


# ---- 构造器取值校验 ----


def test_invalid_policy_rejected_at_construction() -> None:
    with pytest.raises(OrchestrationError) as exc:
        TaskScheduler(
            decomposer=SubtaskDecomposer(),
            router=MultiAgentRouter(),
            state_machine=StateMachine(),
            difficulty_policy="fast",
        )
    assert exc.value.code == OrchestrationErrorCode.INVALID_DISPATCH_POLICY


# ---- LLM 拆解自报难易度 ----


class _FakeLLM:
    """acompletion 桩：固定 content。"""

    def __init__(self, content: str) -> None:
        self._content = content

    async def acompletion(self, request: object) -> object:
        return SimpleNamespace(content=self._content)


def test_planner_parses_difficulty() -> None:
    dag = json.dumps(
        {
            "subtasks": [
                {"id": "1", "goal": "抓取", "acceptance": "非空", "difficulty": "hard"},
                {"id": "2", "goal": "汇总", "acceptance": "存在", "difficulty": "nonsense"},
            ]
        }
    )
    result = asyncio.run(LLMSubtaskPlanner(_FakeLLM(dag))("复合目标"))
    assert [s.difficulty for s in result.subtasks] == ["hard", "medium"]
