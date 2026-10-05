"""上下文压实的**出厂默认阈值**守护（change 0097）。

既有用例（`test_context.py::test_compactor_should_compact_threshold`、
`test_loop.py::_compacting_loop` 一族的 4 例）都以**注入的**阈值验证触发逻辑；
本文件补的是**默认值这一层**：`Compactor()` 的 `round_threshold=10` 与
`DefaultLoop` 的 `token_budget=65536`、以及组合根（`runtime.py`）**未覆盖**二者
这一事实的可观测后果（生产真按 10 轮 / 65536 token 触发）。

阈值语义：`rounds >= round_threshold or token_used >= budget`（`context/compactor.py`）；
`token_budget <= 0` 时仅轮数维度有效（守卫在 `DefaultLoop._should_compact`）。
"""

from __future__ import annotations

from core.context import Compactor
from core.loop import Action, DefaultLoop

_DEFAULT_ROUNDS = 10
_DEFAULT_BUDGET = 65536


def test_default_round_threshold_boundary() -> None:
    """默认轮数阈值 = 10：第 9 轮不触发、第 10 轮触发。"""
    c = Compactor()
    assert c.should_compact(_DEFAULT_ROUNDS - 1, 0, _DEFAULT_BUDGET) is False
    assert c.should_compact(_DEFAULT_ROUNDS, 0, _DEFAULT_BUDGET) is True


def test_default_token_budget_boundary() -> None:
    """默认 token 预算 = 65536：65535 不触发、65536 触发（与轮数维度取或）。"""
    c = Compactor()
    assert c.should_compact(0, _DEFAULT_BUDGET - 1, _DEFAULT_BUDGET) is False
    assert c.should_compact(0, _DEFAULT_BUDGET, _DEFAULT_BUDGET) is True


class _CountingCompactor(Compactor):
    """包一层只记 `compact` 调用次数，判定逻辑完全沿用基类。"""

    def __init__(self) -> None:
        super().__init__()
        self.compacted = 0

    def compact(self, history: list[dict[str, object]]) -> object:  # type: ignore[override]
        self.compacted += 1
        return super().compact(history)


def test_loop_default_wiring_compacts_exactly_once_at_round_ten() -> None:
    """缺省装配（不注入任何阈值）：非终止动作连跑，压实恰在第 10 轮触发**一次**。

    顺带锁住组合根未覆盖 `token_budget`：若默认预算被改成小值，此用例会在第 10 轮前
    因 token 维度提前压实而失败。
    """
    rec = _CountingCompactor()
    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.echo", args={"text": "x"}),
        compactor=rec,
    )

    result = loop.run("hi")

    assert rec.compacted == 1, "默认阈值下恰触发一次压实"
    assert "LOOP_LIMIT_EXCEEDED" in result.reply, "非终止动作由轮数上限终止"
