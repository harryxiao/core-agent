## MODIFIED Requirements

### Requirement: TUI 子 Agent 焦点视图

TUI（REPL）SHALL 支持**主视图 ⇄ 子任务焦点视图**的切换：`/focus <子任务标识>` SHALL 进入该子任务的焦点视图，`/main` 或 `F2` SHALL 返回主视图。

焦点视图 SHALL 呈现该子任务的**标题 + 运行状态**（沿用既有折叠块口径 `⟳` / `✓` / `✗`）与**详情**（验收标准 / 里程碑 / 判定理由 / 结果节选），并随该子任务的里程碑与收尾事件**实时刷新**。

视图数据 SHALL 全部取自既有 `task.*` 事件载荷，SHALL NOT 新建第二数据源，SHALL NOT 接子 Agent 消息流（转录只注入主 loop）；里程碑 SHALL 沿用既有**友好名**呈现（SHALL NOT 暴露内部 `tool_id` 与原始参数）。

切回主视图 SHALL NOT 改变主时间线的**内容**（呈现层切换，非数据层变更）。未知子任务标识 SHALL NOT 切换视图（提示并保持主视图）。焦点命令 SHALL 在任务**运行中**可用（SHALL NOT 被忙态拒绝拦截）。`task_started` 与**审批挂起**时 SHALL 回到主视图。

当存在当前/最近一次任务的**已开工**子任务时，TUI SHALL 在时间线下方（输入区上方）自动呈现**标签栏**：首位 `main`，其后每个已开工子任务一项，标签为题缩写（有界；goal 为空时回退 `子任务 <sid>`）。点击标签 SHALL 切换到对应视图；点击子任务折叠块标题 SHALL 同样进入该子任务焦点视图，且折叠块的展开/收起语义 SHALL 保持不变。

标签 SHALL 随 `subtask_started` / `subtask_completed` 更新状态；`task_started` SHALL 清空旧标签并回到主视图；会话切换（`/resume`）SHALL 清空标签；任务收尾（`task_finished` / `task_failed`）SHALL 保留终态标签与当前视图（快照），直到下一次 `task_started` 或会话切换。标签数据 SHALL 仅取自既有 `task.*` 事件载荷，SHALL NOT 新建第二数据源。

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

#### Scenario: 标签栏自动展示并支持点击切换
- **GIVEN** 一个在途任务且其子任务已开工
- **WHEN** TUI 呈现时间线
- **THEN** 时间线下方出现标签栏，首位为 `main`，其后为该子任务的主题缩写；点击该子任务标签 ⇒ 焦点面板可见、主时间线不可见；点击 `main` ⇒ 主时间线恢复且文本逐字不变

#### Scenario: 点击子任务块标题进入焦点视图
- **GIVEN** 时间线上存在某子任务的折叠块
- **WHEN** 用户点击该折叠块标题
- **THEN** 进入该子任务的焦点视图，且折叠块自身的展开/收起状态仍按既有语义切换

#### Scenario: 收尾保留终态标签，下一次任务重置
- **GIVEN** 已聚焦某子任务且该任务收尾
- **WHEN** `task_finished` / `task_failed` 到达
- **THEN** 标签栏保留该子任务的 ✓ / ✗ 终态且当前焦点视图不被强制切回；下一次 `task_started` 到达时标签栏重置为仅 `main` 并回到主视图

#### Scenario: 会话切换清空标签
- **GIVEN** 标签栏中存在若干子任务标签
- **WHEN** 用户经 `/resume` 切换会话
- **THEN** 标签栏隐藏、标签模型清空，主视图恢复

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

SPA SHALL 在聊天区下方（输入框上方）呈现**标签栏**：首位 `main`，其后为当前/最近任务的每个子任务
（主题缩写）。点击子任务标签 SHALL 将聊天区切换为该子任务的**只读**详情视图（标题 / 状态 / 验收 /
里程碑 / 判定理由 / 结果节选，全部取自既有 `task.*` 事件载荷）；点击 `main` SHALL 立即返回主 Agent
会话。任务区中的子任务行 SHALL 可点击并选中同一视图。输入框 SHALL 仅对主 Agent 生效。

任务收尾 SHALL 保留终态标签与详情快照，直到下一次 `task_started` 或会话切换；下一次任务开始 SHALL
回到 `main` 并清空旧标签。

**进入子 agent 会话 / 向子 Agent 发消息** SHALL NOT 在本 Requirement 内：子 Agent 消息流**无数据源**
（转录只注入主 loop）；上述详情视图 SHALL NOT 新建第二数据源、SHALL NOT 接子 Agent 消息流。

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

#### Scenario: 标签栏展示并切换只读子任务详情

- **GIVEN** 一个在途任务且其子任务已开始执行
- **WHEN** 用户点击聊天区下方的该子任务标签（或任务区的该子任务行）
- **THEN** 聊天区切换为该子任务的只读详情（标题 / 状态 / 验收 / 里程碑 / 理由 / 结果节选），输入框不对子 Agent 生效

#### Scenario: 点击 main 返回主 Agent 会话

- **GIVEN** 聊天区处于某子任务只读详情
- **WHEN** 用户点击 `main` 标签
- **THEN** 立即恢复主 Agent 时间线，且其内容与切换前逐字一致

#### Scenario: 收尾保留快照，下一次任务重置

- **GIVEN** 用户正查看某子任务详情且该任务收尾
- **WHEN** `task_finished` / `task_failed` 到达
- **THEN** 标签与该子任务详情快照保留（终态可见）；下一次 `task_started` 到达后标签重置为仅 `main` 并回到主视图

#### Scenario: 详情只取事件载荷

- **GIVEN** 子 Agent 产生了其内部消息流或思考增量
- **WHEN** Web 呈现该子任务详情
- **THEN** 详情只包含既有 `task.*` 载荷字段（验收 / 里程碑 / 理由 / 结果节选），不出现子 Agent 消息流内容
