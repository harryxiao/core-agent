# UI Specification Delta

## ADDED Requirements

### Requirement: TUI 子 Agent 焦点视图

TUI（REPL）SHALL 支持**主视图 ⇄ 子任务焦点视图**的切换：`/focus <子任务标识>` SHALL 进入该子任务的焦点视图，`/main` 或 `F2` SHALL 返回主视图。

焦点视图 SHALL 呈现该子任务的**标题 + 运行状态**（沿用既有折叠块口径 `⟳` / `✓` / `✗`）与**详情**（验收标准 / 里程碑 / 判定理由 / 结果节选），并随该子任务的里程碑与收尾事件**实时刷新**。

视图数据 SHALL 全部取自既有 `task.*` 事件载荷，SHALL NOT 新建第二数据源，SHALL NOT 接子 Agent 消息流（转录只注入主 loop）；里程碑 SHALL 沿用既有**友好名**呈现（SHALL NOT 暴露内部 `tool_id` 与原始参数）。

切回主视图 SHALL NOT 改变主时间线的**内容**（呈现层切换，非数据层变更）。未知子任务标识 SHALL NOT 切换视图（提示并保持主视图）。焦点命令 SHALL 在任务**运行中**可用（SHALL NOT 被忙态拒绝拦截）。`task_started` 与**审批挂起**时 SHALL 回到主视图。

#### Scenario: 聚焦显示子任务框且主时间线不可见

- **GIVEN** 一个在途任务且其子任务已开工（已有对应折叠块）
- **WHEN** 用户输入 `/focus <该子任务标识>`
- **THEN** 焦点面板可见且标题含该子任务标识与运行态徽标，主时间线不可见，且该输入**不**被送入推理

#### Scenario: 返回主视图后主时间线内容逐字不变

- **GIVEN** 已聚焦某子任务
- **WHEN** 用户输入 `/main` 或按 `F2`
- **THEN** 主时间线可见且其文本与聚焦前**逐字一致**（焦点视图不改主时间线内容）

#### Scenario: 聚焦期间随里程碑与收尾实时刷新

- **GIVEN** 已聚焦某在途子任务
- **WHEN** 该子任务产生里程碑事件（`action_started` / `action_completed` / `step_completed`）或收尾
- **THEN** 焦点面板正文依序补入里程碑（工具类显示友好名与耗时），收尾后标题落 ✓ / ✗ 且正文含判定理由

#### Scenario: 未知子任务标识不切换视图

- **GIVEN** 某标识**没有**对应折叠块（未收到其 `subtask_started`）
- **WHEN** 用户输入 `/focus <该标识>`
- **THEN** 不切换视图（主时间线仍可见），并给出未找到的提示

#### Scenario: 焦点命令在任务运行中可用

- **GIVEN** 一个在途任务（REPL 处于忙态，普通输入会被拒绝）
- **WHEN** 用户输入焦点命令（`/focus <标识>` 或 `/main` / `F2`）
- **THEN** 命令被处理（不被忙态拒绝），且**不**进入推理

#### Scenario: 焦点面板不泄露内部标识与原始参数

- **GIVEN** 已聚焦某子任务且其已产生工具类里程碑
- **WHEN** 焦点面板呈现里程碑
- **THEN** 面板文本含**友好名**（如 `Bash`），且**不含**内部 `tool_id` 与工具原始参数
