# ui — 前台委托子 Agent 的实况标签与只读交互视图（change 0298）

## ADDED Requirements

### Requirement: 前台委托子 Agent 实况视图

主 Agent 经 `tools.delegate` **前台**委托子 Agent 时，系统 SHALL 在主轮事件流中产出：

- `agent.started`：`agent_id`（画像 + 实例后缀，进程内唯一）、`agent`（画像 id）、`title`
  （任务首个非空行、空白折叠、有界）；
- `agent.progress`：`agent_id` + `event`（内层事件类型）+ `data`（**字段白名单**）；
- `agent.completed`：`agent_id` + `ok` + `reply`（有界节选；工具返回值仍为全文）。

子 Agent 进度 SHALL 仅转发白名单内字段（`action_started` / `action_completed` /
`step_completed` / `loop.compacting` / `loop.compacted` 的既有里程碑字段）。表外事件
（含思考增量、回复增量、表外类型）SHALL NOT 外发；系统 SHALL NOT 接子 Agent 的原始
消息流。异常路径 SHALL 先落 `ok=false` 的 `agent.completed`（只含异常类型名）再向上抛。

TUI 与 Web SHALL 在标签栏 `main` 之后追加 `Agent · <标题缩写>` 条目；`agent.completed`
后条目 SHALL 更新为 ✓ / ✗。点击条目 SHALL 切换到该 Agent 的**只读**详情（状态 / 里程碑 /
回复节选）；点击 `main` SHALL 返回主视图且主时间线逐字不变；输入框 SHALL 仅对主 Agent 生效。

新一回合或新任务开始 SHALL 清空上一回合的委托标签；无订阅方（`arun` / 后台
`tools.delegate(background=true)`）SHALL 保持原路径与既有事件面逐字不变。

#### Scenario: 前台委托出现 Agent 标签并可切换

- **GIVEN** 主轮内一次前台 `tools.delegate` 已开始
- **WHEN** 收到 `agent.started`
- **THEN** 标签栏可见且含 `main` 与 `Agent · <标题>`；点击该条目 ⇒ 显示该 Agent 的只读详情，
  主时间线不可见；点击 `main` ⇒ 主时间线恢复且内容逐字不变

#### Scenario: 里程碑实时进入详情

- **GIVEN** 已聚焦某在途委托 Agent
- **WHEN** 收到 `agent.progress`（白名单内类型）
- **THEN** 详情按既有友好名口径补入里程碑；表外类型不落空行、不落占位

#### Scenario: 收尾与异常可见

- **GIVEN** 一次前台委托以成功 / 失败 / 异常结束
- **WHEN** 收到 `agent.completed`
- **THEN** 标签落 ✓ / ✗，详情含回复节选（异常路径只含异常类型名，不含异常正文）

#### Scenario: 不泄露子 Agent 消息流

- **GIVEN** 子 Agent 产生思考增量、回复增量或表外事件
- **WHEN** 父事件流与只读详情呈现
- **THEN** 不出现这些内容（仅白名单里程碑与终态节选）

#### Scenario: 后台委托不再造事件面

- **GIVEN** 以 `background=true` 发起委托
- **WHEN** 父轮次运行
- **THEN** 不产生 `agent.*` 实时事件（仅既有终态完成通知），且前台路径的返回值与超时语义不变
