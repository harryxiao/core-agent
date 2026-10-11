"""压缩轴口径守护（轮 / 步两轴不可互换）—— change 0200 / ADR-0190 / 台账 E137。

规格：doc/openspec/specs/context/spec.md「压缩轴口径（轮 / 步两轴不可互换）」。

**本 change 零 `src/` 改动、零行为改动** ⇒ 这两条是**守护**断言（绿→绿），不是 red→green。
其价值在**反证**：把断言改成轮数读法（如把步轴断言的入参换成 `0`，或把轮轴断言换成固定字面
边界）⇒ **转红** ⇒ 证明两轴分工这一语义被真正钉住，而非恒真。

**不重复既有锚**：`tests/test_context_window.py::test_plan_window_tiered_splits_by_ratio` 已钉住
**某一点**的份额数值（20 轮 ⇒ 短 10 / 中 6）；本文件钉的是**跨两点**的**缩放关系** —— 后者才是
「轮比率」与「字面边界」的判别式（字面边界下两点会**相等**）。
"""

from __future__ import annotations

from core.context import Compactor, plan_window
from core.loop import LoopContext

_BUDGET = 32768

# token 维度**不可满足**的预算：判据为 `token_used >= budget` ⇒ `0 >= _HUGE_BUDGET` 恒假。
# **不得**用 `budget=0` 排除 token 维度 —— 那会让 `0 >= 0` 恒真、token 维度反而**恒触发**。
_HUGE_BUDGET = 10**9


def test_compaction_trigger_axis_is_steps_not_turns() -> None:
    """压实触发由**本轮步数**决定，且步计数每用户轮归零 ⇒「对话轮数」不可表达。

    **不可满足的 token 预算**排除 token 维度 ⇒ 判据只剩步轴一项。用 `Compactor()` 的**出厂
    缺省**（`_STEP_THRESHOLD = 6`）而非显式传参 ⇒ 断言的是**生产默认**语义。
    """
    compactor = Compactor()

    assert compactor.should_compact(6, 0, _HUGE_BUDGET) is True  # noqa: PLR2004 — 出厂步阈值
    assert compactor.should_compact(5, 0, _HUGE_BUDGET) is False  # noqa: PLR2004 — 阈值之下

    # 步计数自本轮起算：新上下文的步计数为 0 ⇒ 系统内**无**跨轮累计可据以推出「对话第 N 轮」。
    assert LoopContext().rounds == 0


def test_window_tier_boundary_scales_with_turns_not_fixed_literal() -> None:
    """分层边界是**轮比率**（随总量等比缩放），**非**固定字面轮数。

    若边界是外来蓝图那种字面区间（`0-5 / 6-20 / 21+`），两点会给出**同一个**边界值。
    """
    assert plan_window(20, _BUDGET, tiered=True).short_turns == 10  # noqa: PLR2004 — 20 × 0.5
    assert plan_window(40, _BUDGET, tiered=True).short_turns == 20  # noqa: PLR2004 — 40 × 0.5
    assert plan_window(40, _BUDGET, tiered=True).mid_turns == 12  # noqa: PLR2004 — 40 × 0.3
