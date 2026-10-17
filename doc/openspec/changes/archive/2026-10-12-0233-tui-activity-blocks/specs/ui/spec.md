## MODIFIED Requirements

### Requirement: 思考过程回显（Think）
系统 SHALL 在**三端**（TUI / Web / APP）以**折叠块**呈现模型的思考原文（`loop.reasoning` 事件），用户可展开查看全文；**同一 ReAct 步**（同一 `round`）的思考增量 SHALL **归并到同一个折叠块**（增量更新，SHALL NOT 逐段新建块）；**不同步** SHALL 使用**不同**折叠块。思考原文 SHALL ONLY 经该事件面呈现，SHALL NOT 写入转录 / 记忆 / 日志 / trace 遥测（思考回显是**纯呈现层**）。

`loop.reasoning` 事件载荷 SHALL 携带思考文本，并 SHALL 携带步标识 `round`（非负整数，与同轮 `action_started.round` 对齐）；若某路径暂时无法提供 `round`，TUI SHALL 降级归并到当前未完成步（或新建一步内块），SHALL NOT 丢弃增量。

折叠的**缺省形态**分端：**TUI** SHALL 缺省**收起**（正文隐藏，仅标题可见；标题 SHALL 为 `Thinking`，进行中 MAY 为 `Thinking…`；**SHALL NOT** 把思考原文刷进标题行），用户点标题 SHALL 可展开查看全文；其标题口径与手势 SHALL 遵循「TUI 步骤块」Requirement（SHALL NOT 在本条内另立冲突口径）；**Web / APP** SHALL 缺省**收起**（承既有形态，逐字不变）。

**未开启**思考回显时（`llm.show_thinking` 缺省 `false`）系统 SHALL NOT 产出该事件、三端呈现 SHALL NOT 出现思考块，事件面与既有缺省**逐字一致**。Web / APP 端 SHALL 复用既有 SSE 事件通道呈现（SHALL NOT 新建端点、SHALL NOT 新建第二数据源）；APP 复用与 Web 相同的 SPA 产物。

#### Scenario: TUI 思考折叠回显
- **GIVEN** 思考回显已开启，且模型逐段返回思考原文
- **WHEN** TUI 消费 `loop.reasoning` 事件
- **THEN** 思考文本落入**单个**步骤块，该块缺省为**收起**（正文不可见）；点标题展开后可见全文；同一 `round` 的增量归并到同一块；主回复呈现不受影响

#### Scenario: 不同 ReAct 步使用不同思考块
- **GIVEN** 思考回显已开启，且连续两个工具步均产生思考原文（`round` 分别为 n 与 n+1）
- **WHEN** TUI 消费对应 `loop.reasoning` 事件
- **THEN** 时间线上出现**两个** Thinking 步骤块（各缺省收起），分别归并各自 round 的增量

#### Scenario: Web 思考折叠回显
- **GIVEN** 思考回显已开启，Web 会话正在流式产出思考原文
- **WHEN** 前端消费 `loop.reasoning` 帧
- **THEN** 思考文本落入**单个**缺省收起的折叠块（`details` 式），增量**追加**到同一块（不逐段新建、不渲染 JSON 载荷），终态帧不改写该块

#### Scenario: 未开启思考回显时三端不呈现
- **GIVEN** 思考回显未开启（缺省），且模型响应携思考原文
- **WHEN** 一轮对话在三端任一端结束
- **THEN** 事件面**不产** `loop.reasoning`，三端呈现中**不出现**思考块，输出与既有缺省**逐字一致**

## REMOVED Requirements

### Requirement: TUI 步骤块（缩略 / 全文 / 收起）

~~旧三态步骤块（缩略 / 全文 / 收起）~~ — **由本 change 替换**：缺省形态改为「收起」，标题口径改为无装饰符号的友好名，手势改为只点标题切换（见 ADDED「TUI 步骤块（活动块）」）。

### Requirement: TUI 回合活动组（Task 壳）

~~外层 `Task(<用户输入摘要>)` 折叠壳~~ — **已撤回**（产品反馈：多一层点击不友好）。

TUI 时间线改回**扁平**呈现：`Thinking…` / 工具步骤块（Read/Bash/…）直接挂时间线；主回复正文正常流式/终态显示；后续若再有思考，继续以 `Thinking…` 同形态追加。SHALL NOT 再建外层 Task 壳。

## ADDED Requirements

### Requirement: TUI 步骤块（活动块：收起 / 展开 / 友好标题）

TUI 的**思考块**与**工具动作块**（及编排规划呈现）SHALL 统一为**步骤块（活动块）**，其缺省形态为**收起**（正文隐藏，仅标题可见）。展开后正文 SHALL **灰显**呈现，超出面板宽度的行 SHALL **折行**完整可见（SHALL NOT 因宽度自适应而被裁掉）。

**标题（无装饰符号）**：步骤块标题 SHALL NOT 以 `⏺` / `▸` / `└` 等作为主标识。工具动作标题 SHALL 使用下列**友好名**与有界摘要（摘要取自白名单结构性字段，单行、超长省略；正文类参数与内部 `tool_id` SHALL NOT 出现在标题中）：

| 来源 | 标题形式 |
|---|---|
| `tools.file_read` | `Read(<path>)` |
| `tools.file_write` | `Write(<path>)` |
| `tools.file_patch` | `Edit(<path>)` |
| `tools.file_delete`（若工具存在） | `Delete(<path>)` |
| `tools.code_run` | `Bash(<script 首行摘要>)` |
| `tools.delegate` | `SubAgent(<task 摘要>)` |
| 编排规划呈现（如 `plan_ready`） | `Planner(<goal 或波次摘要>)` |
| `loop.reasoning` | `Thinking`（进行中 MAY 为 `Thinking…`；SHALL NOT 附思考原文） |

取不到摘要时标题 SHALL 分别为 `Read` / `Write` / `Edit` / `Delete` / `Bash()` / `SubAgent()` / `Planner()` / `Thinking`（不落占位路径、不谎报）。完成态 MAY 在标题追加短后缀（如耗时或失败标记），SHALL NOT 因此恢复 `⏺` 前缀。

**动态标题**：工具步骤块（如 Bash）处于收起且进行中时，TUI SHALL 允许以有界合帧刷新**结构性**标题摘要；**Thinking** 标题 SHALL NOT 随思考增量逐字刷新（避免同行原文闪烁），增量只写入块正文缓冲，收起时正文保持隐藏直至用户展开。

**手势**：点**标题** SHALL 在**收起 ⇄ 展开**之间切换。展开后若实现「末尾有界行预览 ⇄ 全文」，点**正文** MAY 切换该预览；无剩余行时 SHALL NOT 渲染无效展开入口。

本条 SHALL NOT 覆盖**子任务折叠块**与**子 Agent 焦点视图**的布局切换语义（后者另有 Requirement）；子任务内里程碑行若呈现工具动作，SHALL 复用本条友好标题口径。本条不要求实现 `tools.file_delete` 工具本体——仅在该工具存在时映射为 `Delete(...)`。

#### Scenario: 缺省收起且标题无圆点符号
- **GIVEN** 一次工具动作（如 `tools.file_read`）开始
- **WHEN** TUI 渲染该动作的步骤块
- **THEN** 该块缺省**收起**；标题匹配 `Read(...)`（或无 path 时为 `Read`），且**不含** `⏺`

#### Scenario: Bash 与 SubAgent 括号摘要
- **GIVEN** `tools.code_run` 的 script 首行与 `tools.delegate` 的 task 摘要均非空
- **WHEN** TUI 渲染对应步骤块标题
- **THEN** 标题分别为 `Bash(<首行摘要>)` 与 `SubAgent(<task 摘要>)`（摘要单行、有界）

#### Scenario: Planner 规划呈现
- **GIVEN** 编排产生 `plan_ready`（或等价规划事件）
- **WHEN** TUI 呈现该规划
- **THEN** 标题为 `Planner(...)` 形式（可含 goal/波次有界摘要），缺省收起或单行活动标题，SHALL NOT 使用 `⏺`

#### Scenario: 展开后灰显折行
- **GIVEN** 某工具步骤块已展开，正文含远超面板宽度的单行
- **WHEN** TUI 渲染该正文
- **THEN** 正文以灰显样式呈现，且该行按面板宽度**折行**完整可见

#### Scenario: 工具收起态标题动态刷新
- **GIVEN** Bash（或同类工具）步骤块处于收起且仍在接收增量
- **WHEN** TUI 合帧刷新
- **THEN** 标题摘要更新为反映最新结构性增量的有界单行，正文保持隐藏直至用户展开

#### Scenario: Thinking 标题不刷原文
- **GIVEN** Thinking 步骤块处于收起且仍在接收思考增量
- **WHEN** TUI 逐条消费 `loop.reasoning`
- **THEN** 标题保持为 `Thinking` 或 `Thinking…`（不含思考原文片段）；增量写入块正文缓冲且收起时不可见；点标题展开后可见全文

#### Scenario: 思考增量同 round 归并
- **GIVEN** 思考回显已开启，同一 `round` 模型逐段返回思考原文
- **WHEN** TUI 逐条消费 `loop.reasoning` 事件
- **THEN** 增量追加到该 round 的**同一个**收起步骤块（不逐段新建块）
