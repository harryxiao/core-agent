# Spec Delta — ui（0313 plan 模式与 `/task` 收敛）

## MODIFIED Requirements

### Requirement: TUI 子任务运行态与详情

TUI（计划批准后的执行流）SHALL 逐子任务呈现**标题**与**运行状态**（运行中 / 完成 / 失败 / 续跑跳过），并可展开查看该子任务的**详情**（里程碑事件 / 验收标准 / 判定理由 / 结果节选）。详情数据 SHALL 全部取自既有 `task.*` 事件载荷，SHALL NOT 新建第二数据源。

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

## ADDED Requirements

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
fail-closed）。勘察完成后，系统 SHALL 复用编排器的拆解能力产出**计划草案**。

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
- **THEN** 流式产出只读勘察事件，随后产出 `plan.draft_ready`（草案标识 / 目标 / 子任务 /
  波次 / 成功标准）；草案不写入注册表、记忆或检查点；事件载荷不含勘察原文

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
