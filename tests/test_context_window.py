"""三层会话滑窗比例分配（context.window）—— change 0178 / ADR-0169 / 台账 E115。

规格：doc/openspec/specs/context/spec.md「三层窗口比例分配」。
"""

from __future__ import annotations

import pytest

from core.context.window import WindowPlan, plan_window


def test_plan_window_untiered_equals_legacy_bounds() -> None:
    """非分层（冷会话）⇒ 短层 = 全部 `history_turns` 轮 + 全部预算 ⇒ 逐字今天口径。"""
    plan = plan_window(20, 32768, tiered=False)
    assert plan == WindowPlan(short_turns=20, mid_turns=0, short_tokens=32768, mid_chars=0)


def test_plan_window_tiered_splits_by_ratio() -> None:
    """分层 ⇒ 0.5 / 0.3 / 0.2 份额切分（缺省 20 轮 / B=32768）。"""
    plan = plan_window(20, 32768, tiered=True)
    assert plan.short_turns == 10  # noqa: PLR2004 — ceil(20 × 0.5)
    assert plan.mid_turns == 6  # noqa: PLR2004 — ceil(20 × 0.3)
    assert plan.short_tokens == 16384  # noqa: PLR2004 — int(32768 × 0.5)
    assert plan.mid_chars == int(32768 * 0.3) * 2  # change 0245：CJK 混合口径 2 字符/token


@pytest.mark.parametrize(("turns", "budget"), [(0, 32768), (-1, 32768), (20, 0), (20, -5), (0, 0)])
def test_plan_window_recovers_zero_guards(turns: int, budget: int) -> None:
    """关闭回灌（轮数或预算非正）⇒ 全零，不读不注入。"""
    assert plan_window(turns, budget, tiered=True) == WindowPlan(0, 0, 0, 0)


@pytest.mark.parametrize("turns", [1, 2, 3, 20, 100])
def test_plan_window_short_band_never_below_one_turn(turns: int) -> None:
    """短层恒 ≥ 1 轮（分层后仍看得见最近一轮原文）。"""
    assert plan_window(turns, 32768, tiered=True).short_turns >= 1


@pytest.mark.parametrize("turns", [1, 2, 3, 5, 20, 100])
def test_plan_window_mid_never_exceeds_remaining(turns: int) -> None:
    """短 + 中 SHALL NOT 超过总量（无重叠配额）。"""
    plan = plan_window(turns, 32768, tiered=True)
    assert plan.short_turns + plan.mid_turns <= turns


def test_plan_window_monotone_in_turns() -> None:
    """分层后短/中轮数随总量单调不减。"""
    plans = [plan_window(turns, 32768, tiered=True) for turns in range(1, 60)]
    shorts = [p.short_turns for p in plans]
    mids = [p.mid_turns for p in plans]
    assert shorts == sorted(shorts)
    assert mids == sorted(mids)
