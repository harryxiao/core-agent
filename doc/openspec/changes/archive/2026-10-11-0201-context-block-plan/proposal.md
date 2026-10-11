# Proposal 0201 — 上下文区块配比（五区块 / 80-20 安全线）

## 为什么

外部蓝图（`memory-4-layer-architecture.md` §3.3）给出「上下文窗口黄金配比」——系统提示
`20%` / 记忆 `15%` / 窗口 `30%` / 归档 `15%` / 缓冲 `20%`。本仓**没有任何一处**表达这套配比，
且三处预算各自为政、互不知晓：

| # | 预算数 | 落点 | 缺什么 |
|---|---|---|---|
| a | `token_budget = 上下文窗口 − loop.output_reserve` | `loop_limits()` | 是**总量**，不划分 |
| b | `token_budget // 2`（历史回灌） | `DefaultLoop._window_plan` | 只覆盖历史一面 |
| c | **字面量 `2048`** | `LLMPlanner._system_prompt` | **与 (a) 无任何关系** |

其中 (c) 是**真缺陷**而非缺配比：`loop` 侧的 token 预算**从未到达 planner** —— 装配器的
`build(budget=…)` 拿的是一个**自 2026 Q1 起就未变过的硬编码字面量**，与用户在配置里设的
`llm.context_window` / `loop.output_reserve` **完全脱钩**。改窗口大小、改预留，事实注入面
**纹丝不动**。

## 做什么

1. **确定性纯函数** `src/core/context/blocks.py`（新；**零 I/O、零模型调用**，逐条镜像
   `context/window.py:plan_window` 的纪律）：模块常量
   `_SYSTEM_SHARE=0.20 / _MEMORY_SHARE=0.15 / _WINDOW_SHARE=0.30 / _ARCHIVE_SHARE=0.15 /
   _RESERVE_SHARE=0.20`；`plan_blocks(total_budget, *, enabled) -> BlockPlan | None`。
2. **唯一消费者**：`_system_prompt` 的 `budget=2048`。接通方式 —— `LoopContext` 新增
   `token_budget: int = 0`（`perceive()` 置为 `self._token_budget`）；
   `LLMPlanner(block_plan=False)` 构造参；**仅在启用且预算为正时**改用计划的
   `memory_tokens`，否则**仍字面 `2048`**。
3. 配置键 `loop.block_plan`（缺省 `False`）+ 独立访问器 + ConfigSpec 行；组合根把
   `config.block_plan()` 注入**四个 loop** 的全部 planner（与 `max_tokens` 同型）。

## 关键裁决（写入 ADR-0191）

- **20% 缓冲是「上界」，靠「不分配」实现，不是新的减法** —— 否则会与 `loop_limits()` 已有的
  `context_window − output_reserve` **双重预留**。这是外部蓝图模型与本仓模型**唯一重叠、
  唯一可能被重复计数**的地方。
- **五区块不映射到 planner 的十个提示词块**：把五份额摊到十块是**提示词契约重写**，
  不是一次 change。本 change 只让**记忆/事实注入面**这一个面拿到派生额度；其余四块配比
  **仅具咨询性**（如实登记为局限）。
- **不新增第 11 个提示词块、不给 `ContextPack` / `BudgetManager._measure` 加按块记账**
  （会改 `_measure` 语义、打掉两条精确增量用例，收益为零）。

## 不改什么

- `2048` 字面量**在启用面关闭时逐字保留** ⇒ 今日提示词**逐字不变**。
- 不重构 `plan_window` / `Compactor` / `BudgetManager`。
- 不采纳蓝图字面 tier 边界（`0200` / ADR-0190 已裁决）。

## 规格影响

`context` **ADDED** 一条要求「上下文区块配比（五区块 / 80-20 安全线）」（5 Scenario）。
既有 7 条 Requirement 与本 change 无关，**逐字保留**（不做 MODIFIED）。

## 风险

- **开关语义漂移**：若缺省翻成 `True`，事实注入面的额度会在无人察觉的情况下从 `2048` 跳到
  `~9800`。⇒ 新测试用**桩装配器捕获 `build(budget=)`**，把「关 ⇒ 逐字 `2048`」钉成回归锚；
  反证：把缺省翻成 `True` ⇒ 该锚转红。
- **双重预留**：缓冲若实现成减法即与 `output_reserve` 重叠。⇒ 要求明写「靠不分配实现」，
  并由「五块之和 ≤ 总预算」的断言钉住。
- **配比面新增配置键**：本键在**启用面**（`loop.block_plan`），非配额分配面 —— 与 `0182` 的
  `loop.compact_steps` 同性质，`三层窗口比例分配` 原文已明文许可。
