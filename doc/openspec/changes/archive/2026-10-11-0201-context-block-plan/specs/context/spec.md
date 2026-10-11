# Context Specification Delta — 上下文区块配比（change 0201）

## ADDED Requirements

### Requirement: 上下文区块配比（五区块 / 80-20 安全线）

系统 SHALL 提供一个**确定性纯函数** `plan_blocks(total_budget, *, enabled) -> BlockPlan | None`
（`core.context.plan_blocks`）—— 只依赖 stdlib、**零 I/O、零模型调用**，把上下文总预算的
五区块配比收敛为**确定性配额**（纪律同 `三层窗口比例分配` 的 `plan_window`）。

五个份额 SHALL 为**模块常量**，取值为：**系统提示 `0.20` / 记忆 `0.15` / 窗口 `0.30` /
归档 `0.15` / 缓冲 `0.20`**。本**配额分配面** SHALL NOT 新增配置键（同 `_STEP_THRESHOLD` /
`_SHORT_SHARE` 纪律）；启用面另有一键（见下），其性质属**启用面**而**非**配比面。

- `enabled=False` ⇒ SHALL 返回**不产出计划**（`None`）⇒ 调用方 SHALL **逐字保持**其既有字面预算
  ⇒ 既有提示词**逐字不变**（同 `plan_window(tiered=False)` 的「逐字等价」先例）。
- 总预算**非正** ⇒ SHALL 返回 `None`（方向恒为「沿用调用方既有字面量」；此处**刻意不**沿
  `plan_window` 的「全零」口径 —— 本函数的消费者是**提示词预算**，「零配额」与「无配额」
  在消费面上语义不同，唯有 `None` 能表达「不接管」）。
- 启用且预算为正 ⇒ 各块配额 SHALL `>= 0`，且**五块之和 SHALL NOT 超过** `total_budget`。
- **20% 缓冲 SHALL 靠「不分配」实现**（即四个可用块合计不超过 `0.80 × total_budget` 的**上界**），
  SHALL NOT 实现为对总预算的**新一轮减法** —— 总预算 SHALL 为**已扣除**输出预留后的值
  （`loop.output_reserve` 已在 `loop_limits()` 的预算派生中扣除），再次扣除缓冲 SHALL 为
  **双重预留**、**非法**。
- 各块配额 SHALL 随 `total_budget` **单调不减**。

唯一消费者 SHALL 是**记忆 / 事实注入面**的预算（装配器 `build(budget=…)`，经 `LoopContext.token_budget`
透传）。其余四块配比 SHALL **仅具咨询性**，SHALL NOT 参与逐块记账（`ContextPack` /
`BudgetManager` 的度量语义 SHALL 保持不变），SHALL NOT 新增提示词块。

启用面 SHALL 为一**显式开关**（配置键 `loop.block_plan`，缺省**关闭**）：关闭时系统 SHALL
沿用既有字面预算，行为**逐字不变**。

#### Scenario: 关闭时不产出计划（既有提示词逐字不变）

- **GIVEN** 启用面关闭
- **WHEN** 以正的总预算调用 `plan_blocks`
- **THEN** 返回 `None` ⇒ 调用方保持其既有字面预算 ⇒ 提示词与启用前**逐字一致**

#### Scenario: 启用时五份额与 80-20 安全线

- **GIVEN** 启用面开启且总预算为正
- **WHEN** 计算区块计划
- **THEN** 系统提示 / 记忆 / 窗口 / 归档四块分别为总预算的 `0.20 / 0.15 / 0.30 / 0.15`（向下取整），
  缓冲块不低于总预算的 `0.20`

#### Scenario: 启用时五块之和不超过总预算

- **GIVEN** 启用面开启且总预算为正
- **WHEN** 求五块配额之和
- **THEN** 之和 **≤** 总预算（缓冲是**未分配**的余量，**非**另一次减法）

#### Scenario: 非正预算不产出计划

- **GIVEN** 启用面开启
- **WHEN** 以 `0` 或负的总预算调用 `plan_blocks`
- **THEN** 返回 `None`（**不**返回全零配额 —— 消费面据此保持既有字面量）

#### Scenario: 配额随总预算单调不减

- **GIVEN** 启用面开启且总预算 `T` 为正
- **WHEN** 分别以 `T` 与 `T'`（`T' > T`）计算各块配额
- **THEN** 每一块的配额在 `T'` 下**不小于**其在 `T` 下的取值
