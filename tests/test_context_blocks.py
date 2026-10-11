"""上下文区块配比用例（change 0201 / ADR-0191 / 账本 E138）。

两块面：
  * `plan_blocks` —— 确定性纯函数（关 ⇒ 不接管；开 ⇒ 五份额 + 80-20 安全线；非正预算 ⇒ 不接管）
  * **唯一消费者** —— `LLMPlanner._system_prompt` 传给装配器 `build(budget=)` 的那个数
    （**逐字锚**：关时必须是字面 `2048`）
"""

from __future__ import annotations

from typing import cast

from core.context import plan_blocks
from core.llm_provider import LLMProvider
from core.loop import LoopContext
from core.loop.planner import LLMPlanner

_B = 65536
_LEGACY_BUDGET = 2048  # planner 的既有**字面**注入预算（未启用时的逐字锚）


class _CapturingAssembler:
    """桩装配器：只捕获 `build()` 的预算实参（本 change 的唯一消费者面）。"""

    def __init__(self) -> None:
        self.budgets: list[int] = []

    def build(self, task: str, stage: str = "", *, budget: int = 0, session_id: str = "") -> None:
        del task, stage, session_id
        self.budgets.append(budget)


def _ctx() -> LoopContext:
    return LoopContext(messages=[{"role": "user", "content": "任务"}], token_budget=_B)


def _planner(assembler: _CapturingAssembler, *, block_plan: bool = False) -> LLMPlanner:
    # `None` 仅占位（`_system_prompt` 不触碰 LLM）；桩装配器非 `DynamicAssembler` 子类。
    return LLMPlanner(  # type: ignore[arg-type]
        cast("LLMProvider", None), assembler=assembler, block_plan=block_plan
    )


# ---- 纯函数面 ----


def test_disabled_returns_none() -> None:
    """关 ⇒ **不接管**（`None`，非全零）⇒ 调用方保持既有字面预算。"""
    assert plan_blocks(_B, enabled=False) is None


def test_enabled_shares_and_safety_line() -> None:
    """五份额 20/15/30/15 + 缓冲不低于 20%。"""
    plan = plan_blocks(_B, enabled=True)
    assert plan is not None
    assert plan.system_tokens == int(_B * 0.20)
    assert plan.memory_tokens == int(_B * 0.15)
    assert plan.window_tokens == int(_B * 0.30)
    assert plan.archive_tokens == int(_B * 0.15)
    assert plan.reserve_tokens >= _B * 0.20  # 安全线：缓冲是**余量**，只会更大


def test_blocks_do_not_exceed_total() -> None:
    """80-20 安全线：五块之和 SHALL NOT 超总预算（缓冲靠**不分配**实现，非再减一次）。"""
    plan = plan_blocks(_B, enabled=True)
    assert plan is not None
    blocks = (
        plan.system_tokens,
        plan.memory_tokens,
        plan.window_tokens,
        plan.archive_tokens,
        plan.reserve_tokens,
    )
    assert all(block >= 0 for block in blocks)
    assert sum(blocks) <= _B


def test_non_positive_budget_returns_none() -> None:
    """非正预算 ⇒ **不接管**（`0` 会被消费面当作「预算为零」，语义不同）。"""
    assert plan_blocks(0, enabled=True) is None
    assert plan_blocks(-1, enabled=True) is None


def test_quotas_monotonic_in_total() -> None:
    """各块配额随总预算**单调不减**。"""
    for low, high in ((1000, 2001), (2048, _B)):
        lo = plan_blocks(low, enabled=True)
        hi = plan_blocks(high, enabled=True)
        assert lo is not None and hi is not None
        assert hi.system_tokens >= lo.system_tokens
        assert hi.memory_tokens >= lo.memory_tokens
        assert hi.window_tokens >= lo.window_tokens
        assert hi.archive_tokens >= lo.archive_tokens
        assert hi.reserve_tokens >= lo.reserve_tokens


# ---- 消费者面（逐字锚）----


def test_disabled_planner_keeps_literal_budget() -> None:
    """**逐字锚**：缺省关 ⇒ 装配器仍收到字面 `2048`（今日提示词逐字不变）。"""
    assembler = _CapturingAssembler()
    _planner(assembler)._system_prompt(_ctx())
    assert assembler.budgets == [_LEGACY_BUDGET]


def test_enabled_without_budget_keeps_literal_budget() -> None:
    """两重保险：开关开了但 `ctx.token_budget` 为 `0`（未接线）⇒ 仍字面 `2048`。"""
    assembler = _CapturingAssembler()
    _planner(assembler, block_plan=True)._system_prompt(
        LoopContext(messages=[{"role": "user", "content": "任务"}])
    )
    assert assembler.budgets == [_LEGACY_BUDGET]


def test_enabled_planner_uses_derived_memory_budget() -> None:
    """开 + 预算已接线 ⇒ 装配器收到**记忆份额**（loop 预算首次到达 planner）。"""
    assembler = _CapturingAssembler()
    _planner(assembler, block_plan=True)._system_prompt(_ctx())
    plan = plan_blocks(_B, enabled=True)
    assert plan is not None
    assert plan.memory_tokens != _LEGACY_BUDGET
    assert assembler.budgets == [plan.memory_tokens]
