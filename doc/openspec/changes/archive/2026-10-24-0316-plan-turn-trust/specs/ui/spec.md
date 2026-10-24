# Spec Delta — ui（0316 计划轮可信度与可打断性）

## MODIFIED Requirements

### Requirement: 会话级执行模式与计划审批

系统 SHALL 为每个会话维护执行模式 `agent_mode ∈ {quick, plan}`，缺省 `quick`。该模式 SHALL 是
**会话作用域的进程内临时状态**：SHALL NOT 写入会话注册表、SHALL NOT 跨进程共享。模式操作
SHALL 校验会话已登记（未登记 ⇒ `UI_SESSION_NOT_FOUND`）；非法模式值 SHALL 返回
`UI_PLAN_MODE_INVALID`，SHALL NOT 静默归一。

TUI SHALL 在**单一真源命令清单**内提供 `/plan`（进入计划模式）与 `/quick`（返回快速模式），
二者 SHALL 可被既有分发链实际执行。计划模式**只影响下一条用户消息的处理路径**，SHALL NOT
改变权限模式（执行权限与 `quick` 相同）。

计划模式下，用户消息 SHALL 走**计划轮**：以**主 Agent 循环**执行，工具面 SHALL 仅含
`READ` 级风险工具，且 SHALL **显式排除** `tools.delegate`（plan SHALL NOT 自动升级为
delegate）；被排除工具 SHALL 在 schema 与**执行面**双重不可用（模型幻觉调用 SHALL
fail-closed）。勘察完成后，系统 SHALL 复用编排器的拆解能力产出**计划草案**。进入拆解阶段时，
计划轮 SHALL 先产出 `plan.drafting` 阶段事件、再产出 `plan.draft_ready`，使呈现端在拆解等待期
SHALL NOT 继续显示勘察阶段的状态。

计划草案 SHALL 是会话内**临时工件**（`PlanDraft`：草案标识 / 目标 / 子任务 DAG / 波次 /
成功标准），SHALL NOT 落盘、SHALL NOT 进入注册表 / 记忆 / 检查点；同一会话同一时刻 SHALL
至多一份草案，新草案 SHALL 覆盖旧草案。草案呈现 SHALL 含各子任务的目标、依赖与验收标准，
并请求 **y/n** 决断。

`y` SHALL 在**同一会话**以**已批准的计划**驱动编排器执行（SHALL NOT 重新拆解已批准计划；
失败恢复回路内的既有重拆语义不变），并 SHALL 使用与 `quick` 相同的执行权限；`n` SHALL
丢弃草案。草案被**一次性消费**：已批准 / 已放弃 / 已被覆盖的草案标识 SHALL 返回
`UI_PLAN_DRAFT_NOT_FOUND`，SHALL NOT 执行。无论批准或放弃，模式 SHALL 回到 `quick`（执行
失败亦不留在 `plan`）。计划审批挂起期间，y/n 决断输入 SHALL NOT 被命令浮层遮蔽。
未注入只读计划循环或编排器时，计划轮 SHALL 返回 `UI_PLAN_UNAVAILABLE`，SHALL NOT 静默降级
为普通轮；草案拆解失败 SHALL 返回 `UI_PLAN_DRAFT_FAILED`。

#### Scenario: 缺省快速模式与命令切换
- **GIVEN** 一个已登记会话且从未切换过模式
- **WHEN** 查询其执行模式
- **THEN** 为 `quick`；输入 `/plan` 后为 `plan`，再输入 `/quick` 后回到 `quick`

#### Scenario: 非法模式值拒绝
- **GIVEN** 一个已登记会话
- **WHEN** 以 `planx` 等非法值设置执行模式
- **THEN** 返回 `UI_PLAN_MODE_INVALID`，模式保持原值（不静默归一）

#### Scenario: 计划轮只读且排除委托
- **GIVEN** 会话处于 `plan` 模式
- **WHEN** 该轮的工具面被枚举
- **THEN** 只含 `READ` 级工具，**不含** `tools.delegate`；调用任一被排除工具在**执行面**
  fail-closed（返回未知工具，不产生副作用）

#### Scenario: 计划轮产出临时草案
- **GIVEN** 会话处于 `plan` 模式且只读循环与编排器已注入
- **WHEN** 用户发送一条目标消息
- **THEN** 流式产出只读勘察事件，随后产出 `plan.drafting`，再产出 `plan.draft_ready`
  （草案标识 / 目标 / 子任务 / 波次 / 成功标准）；草案不写入注册表、记忆或检查点；事件载荷
  不含勘察原文

#### Scenario: 拆解阶段可见
- **GIVEN** 勘察已结束、拆解调用尚未返回
- **WHEN** 呈现端处理 `plan.drafting`
- **THEN** 状态行显示拆解阶段（不再显示勘察阶段），且该事件先于拆解调用发起被产出

#### Scenario: 批准后同会话执行且回快速模式
- **GIVEN** 一份待决计划草案（含一个子任务）
- **WHEN** 用户输入 `y`
- **THEN** 编排器在**同一会话**按该草案执行（单子任务由主 Agent 自跑），不再重新拆解；
  TUI 呈现 `task.*` 进度事件；会话模式为 `quick`；同一草案标识不可再次执行

#### Scenario: 放弃计划丢弃草案
- **GIVEN** 一份待决计划草案
- **WHEN** 用户输入 `n`
- **THEN** 草案被丢弃（后续以该标识批准返回 `UI_PLAN_DRAFT_NOT_FOUND`），会话模式回到 `quick`

#### Scenario: 计划能力未注入时报错
- **GIVEN** 会话处于 `plan` 模式但只读计划循环（或编排器）未注入
- **WHEN** 用户发送一条目标消息
- **THEN** 返回 `UI_PLAN_UNAVAILABLE`，SHALL NOT 以普通轮静默执行

#### Scenario: 审批挂起期间浮层不遮蔽决断
- **GIVEN** 计划草案已呈现、等待 y/n
- **WHEN** 用户在输入框输入任意内容（含 `/` 起始）
- **THEN** SHALL NOT 呈现命令浮层，y/n 决断语义不变

#### Scenario: 模式为进程内临时状态
- **GIVEN** 一个处于 `plan` 模式的会话
- **WHEN** 检查会话注册表快照
- **THEN** 注册表条目形状与内容不因模式切换而变化（不新增模式字段）

### Requirement: TUI 退出及时性

TUI 用户请求退出（Ctrl+Q）时，进程 SHALL 及时结束：退出路径 SHALL NOT 等待**在途阻塞工作**
（默认执行器线程中的 LLM 流读取、工具执行、钩子外呼等）完成，SHALL NOT 让退出耗时随在途
工作的**剩余时长**增长。

退出 SHALL 保留既有收尾语义：Textual worker SHALL 照常被取消、终端状态 SHALL 照常复原、
解释器级清理（`atexit` 注册的钩子 `close` / MCP 子进程回收 / 插件卸载）SHALL 照常执行。
被放弃的在途工作 SHALL 随进程终止，SHALL NOT 阻塞退出。

空闲退出与一轮正常完成后的退出 SHALL 与既有行为一致。Ctrl+B 打断（停本轮）与 Ctrl+Q
退出（结束进程）语义 SHALL 保持分离。

「打断本轮」SHALL 指取消在途轮次的执行：轮次按既有异常安全路径收尾（忙态复位、已收内容不
丢），进程 SHALL NOT 结束，输入面 SHALL 恢复接受新消息。计划草案处于 y/n 待决时，Ctrl+B
SHALL 等价于放弃草案（草案丢弃、模式回到 `quick`）。无在途轮次时，Ctrl+B SHALL 保持既有
barge-in（TTS 打断）语义，SHALL NOT 结束进程。

#### Scenario: 在途阻塞工作不阻塞退出
- **GIVEN** TUI 正有一轮在途，且其工作线程阻塞在长读（如 LLM 流式响应 / 工具执行）
- **WHEN** 用户按 Ctrl+Q
- **THEN** 进程在**与在途工作剩余时长无关**的短时间内结束；终端状态复原；退出码为 0

#### Scenario: 空闲退出逐字不变
- **GIVEN** TUI 空闲（无在途轮次）
- **WHEN** 用户按 Ctrl+Q
- **THEN** 进程立即结束，行为与既有实现一致

#### Scenario: 打断与退出语义分离
- **GIVEN** TUI 正有一轮在途
- **WHEN** 用户按 Ctrl+B
- **THEN** 仅打断本轮（进程继续运行）；Ctrl+Q 才结束进程

#### Scenario: 打断在途轮次后输入恢复
- **GIVEN** TUI 正有一轮在途（LLM 流未收束）
- **WHEN** 用户按 Ctrl+B
- **THEN** 该轮被取消、忙态复位并明示「已打断本轮」；随后发送的新消息 SHALL 被正常受理
  （进程不退出）

#### Scenario: 打断待决计划草案等价放弃
- **GIVEN** 计划草案已呈现并挂起等待 y/n
- **WHEN** 用户按 Ctrl+B
- **THEN** 草案被丢弃、会话模式回到 `quick`、编排器 SHALL NOT 被驱动；提示「已放弃计划」

#### Scenario: 空闲时 barge-in 语义不变
- **GIVEN** TUI 空闲（无在途轮次、无待决草案）
- **WHEN** 用户按 Ctrl+B
- **THEN** 仅呈现既有 barge-in（TTS 打断）提示，进程不退出、无轮次状态变化
