"""上下文区块配比 —— 五区块 / 80-20 安全线（change 0201 / ADR-0191）。

把上下文总预算按固定份额收敛为**确定性配额**：系统提示 / 记忆 / 窗口 / 归档 / 缓冲。
本模块只承载**策略**（纯函数、零 I/O、零模型调用），纪律逐条镜像 `context.window.plan_window`。

**缓冲是「不分配」的结果，不是一次减法**：总预算已是**扣除输出预留后**的值
（`loop_limits()` 的 `窗口 − loop.output_reserve`）⇒ 若此处再减一次 20%，同一次预留会被扣两遍。

规格：doc/openspec/specs/context/spec.md「上下文区块配比（五区块 / 80-20 安全线）」
"""

from __future__ import annotations

from dataclasses import dataclass

# 五区块份额 —— 模块常量（本**配额分配面**不新增配置键，同 `_STEP_THRESHOLD` /
# `_SHORT_SHARE` 纪律）；四个可用块合计 `0.80`，其余 `0.20` 为**未分配**的缓冲
# （安全线 —— 由「余数」承载，无独立常量）。
_SYSTEM_SHARE, _MEMORY_SHARE, _WINDOW_SHARE, _ARCHIVE_SHARE = 0.20, 0.15, 0.30, 0.15


@dataclass(frozen=True)
class BlockPlan:
    """五区块配额（全为**裸 int** —— 便于消费面直接解包，不携带任何注入面语义）。"""

    total_tokens: int  # 计划所依据的总预算（已扣输出预留）
    system_tokens: int  # 系统提示面份额（**咨询性**：今日不驱动行为）
    memory_tokens: int  # 记忆 / 事实注入面份额（**唯一消费者** —— 装配器 `build(budget=…)`）
    window_tokens: int  # 回灌历史面份额（**咨询性**：该面另有 `token_budget // 2` 口径）
    archive_tokens: int  # 归档 / 压实面份额（**咨询性**：不进 prompt）
    reserve_tokens: int  # 缓冲（**上界**，靠不分配实现）—— 余量，恒 ≥ 总预算的 `0.20`


def plan_blocks(total_budget: int, *, enabled: bool) -> BlockPlan | None:
    """按份额算出五区块配额；**不接管**时返回 `None`。

    `enabled=False` ⇒ `None`（调用方**逐字保持**其既有字面预算 —— 同
    `plan_window(tiered=False)` 的「逐字等价」先例）。总预算**非正** ⇒ 同样 `None`。

    **刻意不沿 `plan_window` 的「全零」口径**：本函数的消费者是**提示词预算**，
    「零配额」与「无配额」在消费面上语义不同（前者会被当作 `budget=0` 传下去），
    唯有 `None` 能表达「不接管」。

    `reserve_tokens` 取**余数**（非 `int(total × 0.20)`）⇒ 五块之和**恰为** `total`，
    且因四个可用块均向下取整，缓冲恒 `≥ 0.20 × total`。
    """
    if not enabled or total_budget <= 0:
        return None
    system = int(total_budget * _SYSTEM_SHARE)
    memory = int(total_budget * _MEMORY_SHARE)
    window = int(total_budget * _WINDOW_SHARE)
    archive = int(total_budget * _ARCHIVE_SHARE)
    return BlockPlan(
        total_tokens=total_budget,
        system_tokens=system,
        memory_tokens=memory,
        window_tokens=window,
        archive_tokens=archive,
        reserve_tokens=total_budget - (system + memory + window + archive),
    )
