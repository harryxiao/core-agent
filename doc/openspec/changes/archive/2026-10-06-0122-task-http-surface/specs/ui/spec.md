# UI Specification Delta

## ADDED Requirements

### Requirement: 任务编排的 HTTP 面与 Web 任务区

统一后端 API 层 SHALL 经 HTTP `POST /task`（请求含会话标识与目标）以 **SSE** 流式返回编排任务的
`task.*` 进度事件，与 TUI `/task`、CLI `task` 走**同一编排器与同一事件面**（SHALL NOT 另造事件面）。
未登记于注册表的会话标识 SHALL 仍被拒绝（`UI_SESSION_NOT_FOUND`）；编排器未注入 SHALL 以结构化错误
（`UI_ORCHESTRATOR_UNSET`）经**错误帧**报告，SHALL NOT 向客户端抛裸异常或静默成功。

SPA SHALL 提供**任务区**，与会话列表**同处右栏位置而各自独立**：任务是**在途**运行态、会话是**持久**
记录，二者 SHALL NOT 合并为同一列表。任务区 SHALL 逐子任务呈现**标题**与**状态**（待执行 / 运行中 /
完成 / 失败），并可展开查看该子任务**详情**（里程碑 / 验收理由 / 失败理由，取自既有事件载荷）；
SHALL NOT 为此新建第二数据源。

任务收尾（`task_finished` / `task_failed`）SHALL 使该任务**移出在途列表**（任务区回落），SHALL NOT
因收尾而进入会话列表（任务不产生会话）。

**进入子 agent 会话 / 主-子焦点切换** SHALL NOT 在本 Requirement 内：子 Agent 消息流**无数据源**
（转录只注入主 loop），故本 Requirement 的「详情」仅指既有事件载荷内可见的字段。

#### Scenario: HTTP 派发任务并流式呈现进度

- **GIVEN** 一个已登记的会话与一个可用编排器
- **WHEN** 经 HTTP `POST /task` 派发一个目标
- **THEN** 以 SSE 依序流式返回该任务的 `task.*` 进度事件（含子任务开始 / 运行态回流 / 收尾），与 TUI `/task` 所见的同一事件面

#### Scenario: 未登记会话标识被拒绝

- **GIVEN** 一个未登记于注册表的 `session_id`
- **WHEN** 经 HTTP `POST /task` 派发任务
- **THEN** 返回 `UI_SESSION_NOT_FOUND` 错误帧（fail-closed，不放宽既有会话校验）

#### Scenario: 编排器未注入时报结构化错误

- **GIVEN** 后端未注入编排器
- **WHEN** 经 HTTP `POST /task` 派发任务
- **THEN** 返回 `UI_ORCHESTRATOR_UNSET` 错误帧（不裸抛、不静默成功）

#### Scenario: 任务区与会话列表并列不混池

- **GIVEN** 界面上既有若干持久会话，又有在途任务
- **WHEN** 打开 Web 界面
- **THEN** 右栏同时呈现任务区与会话列表两个独立区块；任务**不出现**在会话列表中，会话**不出现**在任务区中

#### Scenario: 子任务标题与状态可见、详情可展开

- **GIVEN** 一个在途任务且其子任务已开始执行
- **WHEN** 任务区呈现该任务
- **THEN** 逐子任务显示标题与状态（待执行 / 运行中 / 完成 / 失败），展开可见该子任务的里程碑或验收 / 失败理由

#### Scenario: 任务收尾后回落

- **GIVEN** 一个在途任务
- **WHEN** 该任务收尾（`task_finished` / `task_failed`）
- **THEN** 该任务移出任务区的在途列表（任务区回落），且**不**出现在会话列表中
