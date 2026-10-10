"""上下文压实的**出厂默认阈值**与触发口径守护（change 0097 / 0182）。

既有用例（`test_context.py::test_compactor_should_compact_threshold`、
`test_loop.py::_compacting_loop` 一族的 4 例）都以**注入的**阈值验证触发逻辑；
本文件补的是**默认值这一层**：`Compactor()` 的 `step_threshold=6` 与
`DefaultLoop` 的 `token_budget=65536`、以及组合根（`runtime.py`）是否覆盖二者。

触发口径（change 0182 / ADR-0173 诚实化）：第一参数是**本轮工具步数**（`ctx.rounds`，
每用户轮自 `0` 起算），**非**对话轮数；判据为
`steps >= step_threshold or token_used >= budget`（`context/compactor.py`）；
`token_budget <= 0` 时仅步数维度有效（守卫在 `DefaultLoop._should_compact`）。
压实 SHALL **每轮至多触发一次**（守卫在 `DefaultLoop.astream` 的本轮标记）。
"""

from __future__ import annotations

import asyncio

from core.configuration.manager import _DEFAULT_COMPACT_STEPS
from core.context import Compactor
from core.context.compactor import _STEP_THRESHOLD
from core.loop import Action, DefaultLoop

_DEFAULT_STEPS = 6
_DEFAULT_BUDGET = 65536


def test_step_threshold_constant_is_six() -> None:
    """默认工具步数阈值 = 6（< `loop.max_rounds` 缺省 10 ⇒ 该维度能提前触发）。"""
    assert _STEP_THRESHOLD == _DEFAULT_STEPS


def test_config_default_matches_compactor_default() -> None:
    """配置缺省与压实器常量**同值**：`configuration` 不 import `context`（分层方向），
    默认值因此两地各一份 —— 本用例把「两地」钉成**受门禁约束的两地**。"""
    assert _DEFAULT_COMPACT_STEPS == _STEP_THRESHOLD


def test_default_step_threshold_boundary() -> None:
    """默认步数阈值 = 6：第 5 步不触发、第 6 步触发。"""
    c = Compactor()
    assert c.should_compact(_DEFAULT_STEPS - 1, 0, _DEFAULT_BUDGET) is False
    assert c.should_compact(_DEFAULT_STEPS, 0, _DEFAULT_BUDGET) is True


def test_default_token_budget_boundary() -> None:
    """默认 token 预算 = 65536：65535 不触发、65536 触发（与步数维度取或）。"""
    c = Compactor()
    assert c.should_compact(0, _DEFAULT_BUDGET - 1, _DEFAULT_BUDGET) is False
    assert c.should_compact(0, _DEFAULT_BUDGET, _DEFAULT_BUDGET) is True


def test_step_threshold_is_injectable() -> None:
    """阈值可注入（组合根按 `loop.compact_steps` 注入）。"""
    c = Compactor(step_threshold=3)
    assert c.should_compact(2, 0, _DEFAULT_BUDGET) is False
    assert c.should_compact(3, 0, _DEFAULT_BUDGET) is True


class _CountingCompactor(Compactor):
    """包一层只记 `compact` 调用次数，判定逻辑完全沿用基类。"""

    def __init__(self, step_threshold: int = _STEP_THRESHOLD) -> None:
        super().__init__(step_threshold=step_threshold)
        self.compacted = 0

    def compact(self, history: list[dict[str, object]]) -> object:  # type: ignore[override]
        self.compacted += 1
        return super().compact(history)


def test_loop_default_wiring_compacts_exactly_once() -> None:
    """缺省装配（不注入任何阈值）：非终止动作连跑，压实恰触发**一次**。

    顺带锁住组合根未覆盖 `token_budget`：若默认预算被改成小值，此用例会因 token 维度
    提前压实而仍为一次 —— 断言「一次」而非「何时」，故对预算改动不敏感（改口径的意图：
    压实次数由**每轮至多一次**的规格条款保证，不再依赖「阈值 == 上限」的巧合）。
    """
    rec = _CountingCompactor()
    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.echo", args={"text": "x"}),
        compactor=rec,
    )

    result = loop.run("hi")

    assert rec.compacted == 1, "默认阈值下恰触发一次压实"
    assert "LOOP_LIMIT_EXCEEDED" in result.reply, "非终止动作由轮数上限终止"


def test_loop_step_threshold_triggers_before_limit() -> None:
    """步数阈值 < 上限 ⇒ 压实**确实在终止前**触发（该维度不是死的）。"""
    rec = _CountingCompactor(step_threshold=2)
    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.echo", args={"text": "x"}),
        compactor=rec,
        max_rounds=5,
    )

    async def drive() -> list[int]:
        return [
            rec.compacted async for event in loop.astream("hi") if event.type == "step_completed"
        ]

    seen = asyncio.run(drive())

    # 压实发生于第 2 步的 `step_completed` **之后**（该事件先外发、判定随后执行），
    # 故第 3 步的事件已能看到计数为 1，而终止步（第 5 步）不是首次压实发生的时刻。
    assert seen[0] == 0, "第 1 步未达阈值 ⇒ 未压实"
    assert seen[2] == 1, "第 3 步时压实已发生（早于第 5 步终止）"
    assert seen[-1] == 1, "后续步不再重复压实"


def test_loop_compacts_at_most_once_per_turn() -> None:
    """阈值远小于上限（`步数 >= 阈值` 在阈值步后**步步为真**）⇒ 每轮仍至多一次压实。"""
    rec = _CountingCompactor(step_threshold=2)
    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.echo", args={"text": "x"}),
        compactor=rec,
        max_rounds=6,
    )

    result = loop.run("hi")

    assert rec.compacted == 1, "同轮多次满足判据不得重复压实（避免同轮多次模型调用）"
    assert "LOOP_LIMIT_EXCEEDED" in result.reply
