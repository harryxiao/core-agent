# Orchestration Specification Delta — 检查点会话归因 + task 路径会话接线（change 0190）

## MODIFIED Requirements

### Requirement: 断点续跑
系统 SHALL 支持长任务挂起、恢复与取消（断点续跑）：挂起时持久化执行上下文与中间结果，恢复时从断点继续而非重头执行，取消时释放已占用资源。检查点持久化 SHALL 携带**发起方会话标识**（发起会话的 `session_id`，空串 = 未归属照实记录）；SHALL NOT 写占位值（如 `"default"`）——检查点的会话归属元数据 SHALL 与实际发起会话一致（发起方未携带会话时为空串）。波次检查点与终态检查点 SHALL 同口径。

#### Scenario: 任务挂起
- **GIVEN** 一个长时间运行的任务
- **WHEN** 触发挂起操作
- **THEN** 执行上下文与中间结果被持久化，任务进入 SUSPENDED 状态，已完成的子任务结果不丢失

#### Scenario: 任务恢复
- **GIVEN** 任务处于 SUSPENDED 状态且断点上下文已持久化
- **WHEN** 触发恢复操作
- **THEN** 从断点继续执行，已完成的子任务不重复执行（幂等恢复）

#### Scenario: 任务取消
- **GIVEN** 任务处于运行或挂起状态
- **WHEN** 触发取消操作
- **THEN** 任务终止并释放已占用的执行单元与资源，已持久化的断点上下文按策略清理

#### Scenario: 检查点携带发起会话标识
- **GIVEN** 一次携带会话标识（非空）的任务执行
- **WHEN** 波次收拢或任务终态触发检查点持久化
- **THEN** 检查点的会话归属元数据等于该发起会话标识（非占位值）；未携带会话时为空串（照实记录未归属）

### Requirement: 任务入口与进度事件
系统 SHALL 提供 `core-agent task <目标>` CLI 入口与 TUI REPL `/task <目标>` 命令驱动编排器：流式产出任务进度事件（task_started / plan_ready / wave_started / subtask_started / subtask_progress / subtask_completed / task_checkpoint / task_finished / task_failed），关键节点（拆解、验收、检查点、终态）写入 trace 审计；支持从检查点断点续跑（重建原计划与已完成子任务集，未完成子任务续跑，已完成子任务不重复执行）。

- **子任务运行态回流**：子任务 SHALL 经子 Agent 循环的**流式接口**执行（不再只取终态），其**里程碑事件** SHALL 以 `subtask_progress` 事件**实时**外发，携带 `task_id` / `subtask_id` / 内层事件类型 / 白名单载荷 / 时间戳。里程碑 = 动作开始（`action_started`）、动作完成（`action_completed`）、步进完成（`step_completed`）。回流 SHALL 走编排器既有的进度事件通道（与 `subtask_started` / `subtask_completed` 同源同序），SHALL NOT 另建旁路。
- **回流粒度与载荷白名单**：回流 SHALL 只含**里程碑**事件；模型流式**原文**（`reply_delta`）SHALL NOT 回流（既洪泛又暴露未定稿原文）。`subtask_progress` 的载荷 SHALL **按内层事件类型白名单化**（逐类只带已知字段：`action_started` → round / tool_id / args 摘要，`action_completed` → round / tool_id / ok / duration_ms / output 摘要，`step_completed` → round / failed）；白名单**外**的内层事件类型（含未来新增类型）SHALL NOT 外发。凭据 / 密钥 SHALL NOT 进入事件面（守「密钥只引用不读取」）。
- **附加通道、终态不变**：`subtask_progress` SHALL 是**附加**通道 —— 子任务终态 SHALL 仍归一为 `SubtaskOutcome`，fan-in 校验、依赖结果交接与波次推进判据 SHALL NOT 因回流而改变（未产出任何里程碑事件时，行为与回流前逐字一致）。
- **任务入口会话归因**：CLI `task` 新任务 SHALL 经共享会话注册表铸真会话（mode `cli`，与其他一次性入口同一注册表）并把该会话标识透传至编排器——子任务轨迹 / 记忆 / 转录按该会话归因（与 TUI `/task`、Web 任务入口的发起会话归因同构）；`--resume` 续跑 SHALL **复用检查点携带的发起会话标识**（同一任务跨续跑不分裂会话），检查点未携带有效会话（含旧占位值）时 SHALL 视作未归属（与既往行为逐字一致）并明示提示（不迁移旧数据）。

#### Scenario: CLI 任务入口流式进度
- **GIVEN** 一个复合目标
- **WHEN** 执行 `core-agent task <目标>`
- **THEN** 拆解出子任务 DAG 按依赖序执行，进度事件依序流式输出，验收与检查点写入 trace

#### Scenario: 断点续跑恢复
- **GIVEN** 任务执行中断（进程被杀）且检查点已持久化
- **WHEN** 以同一 task-id 从检查点恢复
- **THEN** 重建原计划并跳过已完成子任务，仅续跑未完成子任务（幂等恢复），已完成子任务结果重建为依赖上下文

#### Scenario: TUI 任务入口流式进度
- **GIVEN** 用户处于 TUI 交互会话（REPL）
- **WHEN** 输入 `/task <目标>`
- **THEN** 任务经编排器流式执行，进度事件依序呈现于会话视图，失败事件可见；任务运行期间普通消息等待，不可并发放任务

#### Scenario: 任务失败可见
- **GIVEN** 某子任务验收失败
- **WHEN** 编排器收拢该波次
- **THEN** 流式产出 task_failed 事件并携带失败子任务与理由，命令以非零退出码结束

#### Scenario: 子任务运行态实时回流
- **GIVEN** 某子任务经子 Agent 循环流式执行
- **WHEN** 内层循环产出里程碑事件（动作开始 / 动作完成 / 步进完成）
- **THEN** 依序外发 `subtask_progress`（携带 task_id / subtask_id / 内层类型 / 白名单载荷），且模型流式原文（`reply_delta`）不外发

#### Scenario: 载荷白名单与非里程碑不外发
- **GIVEN** 内层循环产出的事件（含白名单外类型与内层载荷多带的字段）
- **WHEN** 转译为 `subtask_progress`
- **THEN** 载荷只含该内层事件类型的白名单字段，白名单外的事件类型不外发

#### Scenario: 回流不改变终态判定
- **GIVEN** 一个产出里程碑事件的子任务
- **WHEN** 该子任务收拢
- **THEN** 其终态仍为 `SubtaskOutcome`（验收结果与 `ok` 判定与未回流时逐字一致），fan-in 推进判据不变

#### Scenario: CLI 新任务铸会话归因
- **GIVEN** 操作者执行 `core-agent task <目标>`（无 `--resume`）
- **WHEN** 任务开始执行
- **THEN** 经共享会话注册表铸出会话（mode `cli`）并透传至编排器，子任务轨迹 / 记忆 / 转录按该会话归因，检查点携带该会话标识

#### Scenario: CLI 续跑复用检查点会话
- **GIVEN** 一个携带有效会话标识的未完成检查点
- **WHEN** 执行 `core-agent task --resume <task-id>`
- **THEN** 续跑复用该检查点的会话标识（同一任务不分裂会话）；检查点为旧占位值 / 无会话时视作未归属并明示提示（行为与既往逐字一致）
