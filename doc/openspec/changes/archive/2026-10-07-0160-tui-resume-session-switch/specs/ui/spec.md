## ADDED Requirements

### Requirement: TUI 会话切换（`/resume`）

TUI SHALL 提供 `/resume <会话标识>` 斜杠命令，把交互会话**切换到既有会话**并**还原其内容**：时间线
SHALL 被清空并以目标会话的既有转录**重新铺入**（agent 回复 SHALL 以与实时流式路径**同一**的 Markdown
格式呈现 —— 承「CLI 友好交互」，SHALL NOT 退化为逐行明文；用户消息 SHALL 以 `❯` 回显行呈现）。
切换后**后续轮次** SHALL 落在**目标**会话（`run_loop` / `run_task` SHALL 以新标识调用）。

会话候选取**既有**面（`UIAPILayer.list_sessions()`，SHALL NOT 新建第二数据源），其二级清单 SHALL 由
「CLI 友好交互」的命令浮层呈现；浮层采纳 SHALL 仍**只改写输入框**（`/resume <标识>`）、SHALL NOT 提交。

切换 SHALL **fail-closed 且先验证后落地**：目标会话**未登记**（`session_messages` 拒绝）⇒ SHALL NOT
改动当前会话的**任何**状态（时间线 / 会话标识 / 呈现态**逐字不变**），仅落一行错误。`/resume`
**无参数**（或参数为空）⇒ SHALL 只提示用法、SHALL NOT 切换。

切换 SHALL **仅在本轮执行结束之后**发生（忙碌中 SHALL 拒绝并提示等待，SHALL NOT 与在途轮次并发
改写会话状态）。切换 SHALL 复位**跨会话无意义**的呈现态（子任务折叠块 / 子 Agent 焦点视图 / 动作块 /
思考块 / 流式缓冲），SHALL NOT 残留上一会话的句柄或缓冲。

#### Scenario: 切换会话并还原其内容
- **GIVEN** 当前会话 A，且存在既有会话 B（已登记，其转录含用户消息与含代码围栏的 agent 回复）
- **WHEN** 用户提交 `/resume <B>`
- **THEN** 时间线被清空并铺入 **B** 的既有转录：B 的 agent 回复渲染为 **Markdown**（围栏成代码块）、
  用户消息以 `❯` 回显行呈现
- **AND THEN** 切换后的**后续轮次**落在 **B**（`run_loop` / `run_task` 收到标识 `<B>`）

#### Scenario: 未登记会话 fail-closed（当前会话逐字不变）
- **GIVEN** 当前会话 A、时间线已有内容
- **WHEN** 用户提交 `/resume <未登记标识>`
- **THEN** **不切换**：时间线内容、当前会话标识与呈现态**逐字不变**，仅落一行错误

#### Scenario: `/resume` 无参数只提示用法
- **GIVEN** TUI 就绪
- **WHEN** 用户提交 `/resume`
- **THEN** 只提示用法、SHALL NOT 切换会话、SHALL NOT 改动时间线

#### Scenario: 本轮执行期间拒绝切换
- **GIVEN** 一轮执行**尚未结束**（忙碌）
- **WHEN** 用户提交 `/resume <已登记标识>`
- **THEN** 拒绝切换（提示处理中）、当前会话与时间线**逐字不变**
