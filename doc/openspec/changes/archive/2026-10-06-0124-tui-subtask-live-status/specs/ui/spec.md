# UI Specification Delta

## ADDED Requirements

### Requirement: TUI 子任务运行态与详情

TUI（REPL `/task`）SHALL 逐子任务呈现**标题**与**运行状态**（运行中 / 完成 / 失败 / 续跑跳过），并可展开查看该子任务的**详情**（里程碑事件 / 验收标准 / 判定理由 / 结果节选）。详情数据 SHALL 全部取自既有 `task.*` 事件载荷，SHALL NOT 新建第二数据源。

里程碑事件（`subtask_progress`，载荷已由编排层按内层类型白名单化）SHALL 被渲染为**用户可见**文本：工具类里程碑 SHALL 复用既有工具动作行的**友好名**呈现（SHALL NOT 暴露内部 `tool_id` 与原始参数），轮次级里程碑 SHALL 呈现轮次与成败。白名单**表外**的事件类型 SHALL NOT 产生任何呈现（不落空行、不落占位、不谎报里程碑）。

**进入子 agent 会话 / 主-子焦点切换** SHALL NOT 在本 Requirement 内：子 Agent 消息流**无数据源**（转录只注入主 loop），故本 Requirement 的「详情」仅指既有事件载荷内可见的字段。

#### Scenario: 子任务运行中可见状态徽标

- **GIVEN** 一个在途任务且其子任务已开工
- **WHEN** TUI 时间线呈现该子任务折叠块
- **THEN** 标题含**运行中**标记；该子任务收尾后标题落 ✓ / ✗（续跑跳过落「已完成（续跑跳过）」）

#### Scenario: 里程碑事件展开可见

- **GIVEN** 子任务执行中产生里程碑事件（`action_started` / `action_completed` / `step_completed`）
- **WHEN** 该子任务折叠块被展开
- **THEN** 依序可见各里程碑（工具类显示友好名与耗时，轮次级显示轮次与成败），且**不含**原始工具参数

#### Scenario: 表外事件不呈现

- **GIVEN** 编排层未外发某一事件类型（白名单表外类型按既有口径静默丢弃）
- **WHEN** TUI 呈现该子任务详情
- **THEN** 详情不出现该类型的内容（不落空行与占位，不谎报里程碑）

#### Scenario: 里程碑先于折叠块到达时静默忽略

- **GIVEN** 某 `subtask_progress` 事件的子任务标识**没有**对应折叠块（未收到其 `subtask_started`）
- **WHEN** TUI 处理该事件
- **THEN** 静默忽略（不新建折叠块、不抛裸异常、不影响其它子任务的详情）
