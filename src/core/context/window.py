"""三层会话滑窗比例分配（change 0178 / ADR-0169）。

会话历史回灌由「单条固定窗口」升级为**三层滑窗**——短层（原文逐字）/ 中层（模型摘要）/ 长层
（会话整体摘要），并按固定份额**动态按比例**分配历史预算。

本模块只承载**策略**（纯函数、零 I/O、零模型调用）：给定 `history_turns` 与历史预算，算出各层
配额。切日志的**机制**留在 `core.memory.transcript.TranscriptStore.window()` —— 反向依赖
（memory → context）会与 `context.compactor` 的 `memory` import 构成循环，违 ADR-0045。

规格：doc/openspec/specs/context/spec.md「三层窗口比例分配」
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# 三层历史预算份额 —— 「动态按比例压缩」的配比（短 0.5 / 中 0.3 / 长 0.2）；
# 仅短、中两层需显式配额，长层以会话摘要形式覆盖更早全部内容（无轮数/字符配额）。
_SHORT_SHARE, _MID_SHARE = 0.5, 0.3

# 字符 / token 换算（与 `context.budget.estimate_tokens` 的 `len // 4` 同口径）
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class WindowPlan:
    """三层滑窗的配额计划（全为**裸 int**，便于跨层解包，不携带 TranscriptStore 语义）。"""

    short_turns: int  # 短层轮数（最近 N 轮原文）
    mid_turns: int  # 中层轮数（紧随短层之前，待摘要）
    short_tokens: int  # 短层 token 上界
    mid_chars: int  # 中层摘要产物字符上界


def plan_window(history_turns: int, history_budget: int, *, tiered: bool) -> WindowPlan:
    """按份额算出三层配额。

    `tiered=False`（冷会话 / 未注入摘要器）⇒ 与既有「双重上界」**逐字等价**
    （短层 = 全部轮数 + 全部预算，中层零）—— 零回归锚点。
    轮数或预算非正 ⇒ 全零（关闭回灌）。
    """
    if history_turns <= 0 or history_budget <= 0:
        return WindowPlan(0, 0, 0, 0)
    if not tiered:
        return WindowPlan(history_turns, 0, history_budget, 0)
    short = min(history_turns, max(1, math.ceil(history_turns * _SHORT_SHARE)))
    mid = max(0, min(history_turns - short, math.ceil(history_turns * _MID_SHARE)))
    return WindowPlan(
        short_turns=short,
        mid_turns=mid,
        short_tokens=max(1, int(history_budget * _SHORT_SHARE)),
        mid_chars=max(0, int(history_budget * _MID_SHARE) * _CHARS_PER_TOKEN),
    )
