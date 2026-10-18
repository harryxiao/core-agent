## ADDED Requirements

### Requirement: 后台委托与完成通知

系统 SHALL 支持**后台委托**：`tools.delegate` 接受可选参数 `background`（缺省 `false`）；
为 `true` 时 SHALL 立即返回 `task_id` 与 `running` 状态，SHALL NOT 阻塞主循环等待子 Agent。
为 `false`（或省略）时既有阻塞委托语义 SHALL 逐字不变。

后台委托 SHALL 有界：运行中的后台任务上限 SHALL 为 8；超限 SHALL 以结构化失败返回
（`ok=false`），SHALL NOT 排队或静默丢弃。每个后台任务 SHALL 落在
`running → done | failed | cancelled` 之一，终态 SHALL 不可变。

完成通知 SHALL 按**会话**记录，并在该会话**下一轮轮首**一次性投递（取走后清除）；
通知 SHALL 有界（每会话待投递 ≤ 32 条，超出丢弃最旧）。系统 SHALL 提供模型侧只读任务
清单（`tools.tasks` 的 `list` / `status`），SHALL NOT 因查询而清空通知。

子 Agent 的工具面 SHALL 继续不含 `tools.delegate` 与 `tools.tasks`（结构上不可再委托、
不可跨 Agent 查看清单）。

#### Scenario: 后台委托立即返回

- **GIVEN** 一个可匹配的子 Agent 且运行中后台任务未达上限
- **WHEN** 模型调用 `tools.delegate(task=..., background=true)`
- **THEN** 工具结果 SHALL 立即返回 `{ok: true, task_id, agent, status: "running"}`
- **AND THEN** 子 Agent 仍在后台执行，主循环 SHALL NOT 等待其完成

#### Scenario: 缺省阻塞语义不变

- **GIVEN** 调用未带 `background`（或显式 `false`）
- **WHEN** 主循环发起委托
- **THEN** 工具 SHALL 等待子 Agent 完成并回传 reply，与引入后台能力前逐字一致

#### Scenario: 完成后通知在下一轮投递且只投一次

- **GIVEN** 某个后台任务已完成（done / failed / cancelled）
- **WHEN** 该会话下一轮开始
- **THEN** 通知 SHALL 以独立块注入模型上下文，含 task_id / agent / 状态 / 有界摘要
- **AND THEN** 再次开始一轮 SHALL NOT 重复投递同一通知

#### Scenario: 通知按会话隔离

- **GIVEN** 会话 A 与会话 B 各有后台任务
- **WHEN** 会话 A 的下一轮开始
- **THEN** SHALL ONLY 投递 A 的通知，B 的通知 SHALL 保持待投递

#### Scenario: 后台任务有界

- **GIVEN** 运行中的后台任务已达上限 8
- **WHEN** 再发起一个后台委托
- **THEN** 工具 SHALL 返回结构化失败（`ok=false`），SHALL NOT 启动第 9 个任务

#### Scenario: 任务清单只读可查

- **GIVEN** 本进程曾发起后台委托
- **WHEN** 模型调用 `tools.tasks` 的 `list` 或 `status`
- **THEN** SHALL 返回任务状态与有界结果摘要；未知 `task_id` SHALL 返回 `found=false`；
  该调用 SHALL NOT 清空待投递通知

#### Scenario: 子 Agent 不可窥视或再委托

- **GIVEN** 子 Agent 独立 loop 的工具面
- **WHEN** 检查其工具清单
- **THEN** SHALL NOT 含 `tools.delegate` 或 `tools.tasks`
