# Orchestration Specification

## Purpose
任务规划与编排把单一循环升级为可处理长周期复杂任务的执行引擎，提供状态机管理、子任务拆解、多 Agent 协同三层基础能力，并新增并行扇出、目标监控、优先级调度三项运行时能力，确保复杂目标可并行推进、可量化校验、可按优先级调度。并行扇出的执行单元显式复用异步接口（acompletion / ainvoke），消除同步串行阻塞。

## Requirements

### Requirement: 任务状态机
系统 SHALL 用显式状态机管理任务状态，只允许合法状态转移，并检测死循环/跑偏。

#### Scenario: 合法状态转移
- **GIVEN** 任务处于 `PLANNING` 状态
- **WHEN** 拆解完成进入 `EXECUTING`
- **THEN** 转移被接受，任务状态更新

#### Scenario: 非法状态转移被拒绝
- **GIVEN** 任务处于 `CREATED` 状态
- **WHEN** 尝试直接跳转到 `DONE`
- **THEN** 转移被拒绝并返回 `INVALID_TRANSITION`

#### Scenario: 检测到死循环
- **GIVEN** 任务在多轮执行后未向目标推进
- **WHEN** 进度哨兵检测到重复模式
- **THEN** 触发 `RECOVERING`（注入换策略提示或转人工）

### Requirement: 子任务拆解
系统 SHALL 将大目标拆解为带验收标准的分步子任务，按依赖拓扑序执行，并逐步校验。子任务交给子 Agent 执行时
SHALL 携带**发起方会话标识**（可选的 `session_id`，缺省空串 = 未归属），使子任务轨迹按**发起会话**归属
（而非落入全局未归属条目）；空标识时归属语义 SHALL 与既往**逐字一致**。

子任务验收失败 SHALL 进入**有限恢复回路**：先仅对**失败子任务**重试一次（已完成子任务 SHALL NOT
重跑），仍失败则**重新拆解一次**（保留原目标与已定成功标准；新计划 SHALL 清空旧计划的完成集与
结果上下文，避免子任务 id 复用导致误跳过或脏依赖）；恢复预算耗尽 SHALL 转 `FAILED`，错误码
沿用最后一次失败原因。子 Agent 执行抛出结构化异常 SHALL 归一为子任务失败并进入同一恢复回路，
SHALL NOT 让异常穿透调度器。空计划（无任何子任务）SHALL 判失败，SHALL NOT 以「空标准视为通过」
误判 `DONE`。

#### Scenario: 拆解与拓扑执行
- **GIVEN** 一个复杂目标
- **WHEN** 拆解器生成子任务 DAG
- **THEN** 子任务按依赖拓扑序执行，无依赖项可并行

#### Scenario: 子任务轨迹按发起会话归属
- **GIVEN** 一次携带会话标识（非空）的任务派发
- **WHEN** 子 Agent 执行子任务并沉淀轨迹
- **THEN** 轨迹条目的 `session_id` 等于该发起方会话标识

#### Scenario: 未携带会话标识时归属不变
- **GIVEN** 一次未携带会话标识的任务派发
- **WHEN** 子 Agent 执行子任务并沉淀轨迹
- **THEN** 轨迹条目 `session_id` 为空串（归全局层），与既往语义逐字一致

#### Scenario: LLM 拆解产出子任务 DAG
- **GIVEN** 拆解器注入 LLM planner
- **WHEN** 输入一个复合目标
- **THEN** planner 经模型调用产出子任务 DAG（id/goal/acceptance/depends_on/difficulty），按依赖拓扑序与波次执行

#### Scenario: LLM 拆解失败回落单子任务
- **GIVEN** 拆解器注入 LLM planner
- **WHEN** 模型调用失败或输出不可解析为合法子任务集
- **THEN** 回落为单子任务（目标即子任务），任务不因此中断

#### Scenario: 依赖结果交接
- **GIVEN** 子任务 B 依赖子任务 A 且 A 验收通过
- **WHEN** B 开始执行
- **THEN** A 的验收通过结果作为前置上下文注入 B 的执行输入，结果随检查点持久化供续跑重建

#### Scenario: 子任务校验通过才推进
- **GIVEN** 一个子任务执行完成
- **WHEN** 结果未通过其验收标准
- **THEN** 不推进下一步，回退重试（有限次）或重新规划

#### Scenario: 重试只重跑失败子任务
- **GIVEN** 一波次内子任务 A 验收通过、子任务 B 验收失败
- **WHEN** 调度器进入重试
- **THEN** 仅 B 被重新执行一次（`subtask_started` 携带 `attempt=2`），A 不被重跑

#### Scenario: 重试通过后继续推进
- **GIVEN** 子任务首次验收失败
- **WHEN** 重试后验收通过
- **THEN** 该子任务记录完成，任务继续推进并最终可达 `DONE`（`replans=0`）

#### Scenario: 重试仍失败触发重新拆解
- **GIVEN** 子任务首次与重试均未通过验收
- **WHEN** 恢复回路仍有重新拆解预算
- **THEN** 任务转入 `RECOVERING`，以原目标、已完成摘要与失败原因重新拆解一次后重入执行

#### Scenario: 恢复预算耗尽转 FAILED
- **GIVEN** 重试与重新拆解预算均已用尽
- **WHEN** 子任务仍未通过验收或目标仍未达成
- **THEN** 任务转 `FAILED`，`task_failed` 携带最后一次失败原因与 `attempts` / `replans` 计数

#### Scenario: 执行异常归一为子任务失败
- **GIVEN** 子 Agent 执行抛出结构化异常
- **WHEN** fan-out 回收结果
- **THEN** 该子任务归一为失败（保留结构化错误码），进入同一重试/重拆回路，异常不穿透调度器

#### Scenario: 空计划不误判完成
- **GIVEN** 检查点或 planner 产出不含任何子任务的计划
- **WHEN** 调度器开始执行
- **THEN** 任务判 `FAILED`（`task_failed`），不因「空成功标准视为通过」而判 `DONE`

### Requirement: 子任务验收门
系统 SHALL 对带验收标准的子任务结果经 LLM 对照判定（验收门）：判定通过才记录完成并推进；判定不通过或判定器不可用时标记失败不推进（fail-closed）；无验收标准时退化为离线非空判定，不调用模型。子任务**执行单元**返回**失败态**（循环未达成目标 / 异常终止 / 预算耗尽）时，验收门 SHALL 判**不通过**（fail-closed），SHALL NOT 因合成回复非空而通过；该失败态 SHALL 传播至子任务终态（`ok = 验收通过 且 执行未失败`）与 fan-in 推进判据。

#### Scenario: 验收门 LLM 判定
- **GIVEN** 子任务带验收标准且执行完成
- **WHEN** 验收门对照 acceptance 判定结果
- **THEN** 判定通过才记录完成并推进下一波次，判定结论与理由写入 trace

#### Scenario: 验收判定失败不推进
- **GIVEN** 子任务结果未达验收标准（或判定调用失败）
- **WHEN** 验收门判定不通过
- **THEN** 子任务标记失败（含理由），不静默推进，任务转入 RECOVERING

#### Scenario: 无验收标准离线判定
- **GIVEN** 子任务未定义验收标准
- **WHEN** 验收门校验结果
- **THEN** 退化为离线判定（结果非空即通过），不调用模型

#### Scenario: 执行失败态不因非空合成回复通过
- **GIVEN** 子任务执行单元返回失败态（`failed=True`）却产出非空回复
- **WHEN** 验收门校验结果
- **THEN** 该子任务标记失败（含理由），不记录完成、不推进后继波次，任务转入 RECOVERING

### Requirement: 多 Agent 协同
系统 SHALL 支持按任务类型路由到最合适的子 Agent，并通过标准化消息协议完成交接。

#### Scenario: 能力匹配与交接
- **GIVEN** 一个子任务需要特定能力
- **WHEN** 路由器匹配到合适的子 Agent
- **THEN** 通过 TaskHandoff 交接，交接上下文由 context 模块打包

#### Scenario: 无匹配 Agent
- **GIVEN** 没有子 Agent 能处理当前子任务，且无可用 fallback
- **WHEN** 路由器打分无命中
- **THEN** 抛出 NO_AGENT_MATCH，调度器捕获并标记子任务失败

### Requirement: 断点续跑
系统 SHALL 支持长任务挂起、恢复与取消（断点续跑）：挂起时持久化执行上下文与中间结果，恢复时从断点继续而非重头执行，取消时释放已占用资源。检查点持久化 SHALL 携带**发起方会话标识**（发起会话的 `session_id`，空串 = 未归属照实记录）；SHALL NOT 写占位值（如 `"default"`）——检查点的会话归属元数据 SHALL 与实际发起会话一致（发起方未携带会话时为空串）。波次检查点与终态检查点 SHALL 同口径。

检查点 SHALL 持久化**重新拆解计数**（`Plan.replans`）；续跑重建 SHALL 保留该计数，SHALL NOT
重置为 0。子任务重试次数为**进程内**有界计数，不跨进程持久化。

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

#### Scenario: 续跑保留重新拆解计数
- **GIVEN** 一次任务已用掉重新拆解预算（`Plan.replans=1`）并写入检查点
- **WHEN** 进程退出后从该检查点续跑
- **THEN** 重建的 `Plan.replans` 仍为 1，恢复回路不会再次获得重新拆解预算

### Requirement: 并行扇出
系统 SHALL 支持并行扇出（fan-out/fan-in）波次调度：子任务按依赖拓扑分层为波次（wave），同一波次内无依赖子任务并行执行，波次全部完成并经 fan-in 汇总校验后推进下一波次，并行度受资源上限约束。

#### Scenario: 波次划分与并行扇出
- **GIVEN** 子任务 DAG 中存在无相互依赖的子任务
- **WHEN** 拆解完成并进入执行
- **THEN** 同波次子任务并行 fan-out 到多个执行单元，不再串行

#### Scenario: fan-in 汇总推进
- **GIVEN** 某波次全部子任务执行完成
- **WHEN** fan-in 汇总校验结果
- **THEN** 校验通过则推进下一波次，失败则触发状态机 RECOVERING

#### Scenario: 资源上限约束
- **GIVEN** 波次内并行子任务数超过资源上限
- **WHEN** 调度并行扇出
- **THEN** 分批执行，同时并行数不超过上限

#### Scenario: fan-out 幂等派发
- **GIVEN** 同一子任务因重试或网络抖动被重复派发
- **WHEN** fan-out 调度收到重复派发请求
- **THEN** 按子任务唯一标识去重，同一子任务仅执行一次，重复派发被忽略

### Requirement: 目标监控
系统 SHALL 用 Goal 与 SuccessCriteria（SMART：具体/可度量/可达成/相关/有时限）定义任务级成功标准，子任务验收标准对齐父目标，并由 ProgressTracker 追踪每子任务进度与整体目标推进，进度未达标时触发重试或重规划。

#### Scenario: 成功标准定义
- **GIVEN** 任务进入拆解
- **WHEN** 定义 Goal 与 SuccessCriteria
- **THEN** 成功标准可判定真伪、可度量（SMART）

#### Scenario: 进度追踪
- **GIVEN** 任务执行中
- **WHEN** 子任务推进
- **THEN** ProgressTracker 更新该子任务进度并反映到整体目标推进

#### Scenario: 未达标重试/重规划
- **GIVEN** 子任务进度未达标
- **WHEN** 进度监控检测到偏差
- **THEN** 触发重试或重新规划（衔接状态机 RECOVERING）

### Requirement: 优先级调度
系统 SHALL 支持子任务 priority 优先级字段，就绪队列（同波次无依赖子任务）按优先级降序调度，同优先级按入队序（FIFO）稳定执行，priority 缺省时取默认值。

#### Scenario: 优先级排序
- **GIVEN** 多个就绪子任务优先级不同
- **WHEN** 就绪队列调度
- **THEN** 按优先级降序执行

#### Scenario: 同优先级稳定序
- **GIVEN** 就绪子任务优先级相同
- **WHEN** 就绪队列调度
- **THEN** 按入队序（FIFO）稳定执行

#### Scenario: 优先级缺省
- **GIVEN** 子任务未指定 priority
- **WHEN** 就绪队列调度
- **THEN** 按默认优先级处理

### Requirement: 异步执行单元契约
系统 SHALL 明确并行扇出的执行单元契约：扇出派发的每个执行单元复用 llm-provider 的 acompletion 与 tool-use 的 ainvoke 异步接口，支持事件循环内非阻塞与真并发执行，消除同步串行阻塞；同一波次内无依赖子任务经异步接口并发派发，不再是串行阻塞。

- **收尾回路不阻塞**：任务完成回调（`on_done`）SHALL 经 `asyncio.to_thread` **卸载**至工作线程执行，SHALL NOT 在事件循环上同步阻塞 —— 回调若承载模型调用等重活，SHALL NOT 阻塞流式产出与已派发的并发。该卸载 SHALL NOT 改变回调的**调用时机与次数**（仍在 `DONE` 达成后调用一次）与终态判定。

#### Scenario: 执行单元复用异步接口
- **GIVEN** 并行扇出派发某波次内的无依赖子任务
- **WHEN** 执行单元发起模型调用或工具调用
- **THEN** 复用 acompletion / ainvoke 异步接口，而非同步 completion / invoke

#### Scenario: 扇出真并发非阻塞
- **GIVEN** 同一波次内多个无依赖子任务
- **WHEN** fan-out 经异步接口并发派发
- **THEN** 各执行单元真并发执行且不阻塞事件循环，总耗时约等于最慢单个执行单元而非各单元耗时之和

#### Scenario: 契约空白闭合
- **GIVEN** 扇出执行单元与 LLMProvider / ToolProvider 异步能力之间存在契约空白
- **WHEN** 本契约显式映射执行单元到异步接口
- **THEN** 并行编排与异步能力之间的契约空白被闭合，扇出场景不再退化为同步串行阻塞

#### Scenario: 完成回调不阻塞事件循环
- **GIVEN** 任务达成 `DONE` 且注入了完成回调（回调内含阻塞工作）
- **WHEN** 编排器触发完成回调
- **THEN** 回调在**工作线程**（非事件循环线程）执行，流式产出不被同步阻塞；回调的调用时机与次数不变（`DONE` 后一次）

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

### Requirement: 难易度感知的调度策略
系统 SHALL 为子任务提供难易度字段 `difficulty`（三档 `easy` / `medium` / `hard`，缺省 `medium`；取值 SHALL 先去除首尾空白并大小写归一，再判集合成员，集合外归一为 `medium`，不抛裸异常、不阻断拆解），并 SHALL 提供**可配置**的同波次调度策略：策略取 `off`（缺省）时，同波次无依赖子任务 SHALL 按依赖拓扑并发扇出（并发度受 `max_concurrency` 上限约束，与引入本策略前**逐字一致**）；策略取 `difficulty` 时，同波次内**存在** `difficulty = hard` 的子任务则该波次 SHALL **串行**执行（按优先级降序逐个），否则维持并发。依赖拓扑 SHALL 仍是**硬约束**（有依赖的子任务必分属不同波次，本策略 SHALL NOT 改变波次划分）。策略取值与并发上限 SHALL 经配置面（ConfigSpec 单一真源）解析，并由**组合根**注入 `TaskScheduler` —— `max_concurrency` SHALL NOT 依赖构造缺省。

#### Scenario: 缺省策略维持既有并发
- **GIVEN** `difficulty_policy` 取缺省 `off`
- **WHEN** 某波次含多个互不依赖的子任务
- **THEN** 该波次并发扇出、并发峰值受 `max_concurrency` 约束，行为与引入本策略前逐字一致

#### Scenario: 难易度策略下含 hard 的波次串行
- **GIVEN** `difficulty_policy` 取 `difficulty`，且某波次含至少一个 `difficulty = hard` 的子任务
- **WHEN** 调度该波次
- **THEN** 该波次串行执行（并发峰值为 1），按优先级降序逐个执行

#### Scenario: 难易度策略下无 hard 的波次并发
- **GIVEN** `difficulty_policy` 取 `difficulty`，且某波次子任务全为 `easy` / `medium`
- **WHEN** 调度该波次
- **THEN** 该波次并发扇出，并发峰值受 `max_concurrency` 约束

#### Scenario: 难易度缺省与非法值归一
- **GIVEN** 子任务未声明 `difficulty`，或模型输出的难易度取值归一后不在三档之内
- **WHEN** 构造子任务
- **THEN** `difficulty` 取 `medium`（归一而非抛错，拆解不因此失败）

#### Scenario: 难易度大小写与空白归一
- **GIVEN** 模型输出 `difficulty` 为 `"HARD"` / `" hard "` / `"Easy"` 等大小写或空白变体
- **WHEN** 构造子任务
- **THEN** 归一为对应小写档位（`hard` / `easy`），而非因字面不等而降级为 `medium`

#### Scenario: 难易度随计划持久化往返
- **GIVEN** 一个含 `difficulty` 的计划被持久化为检查点
- **WHEN** 经 `plan_to_dict` / `plan_from_dict` 往返重建
- **THEN** 每个子任务的 `difficulty` 与持久化前一致（不静默丢字段）；旧检查点缺该字段时回落 `medium`

#### Scenario: 并发上限与策略由配置注入
- **GIVEN** 配置面设置了 `orchestration.max_concurrency` 与 `orchestration.difficulty_policy`
- **WHEN** 组合根装配 `TaskScheduler`
- **THEN** 调度器按配置值执行（非构造缺省）；配置取值非法时校验期阻断启动
