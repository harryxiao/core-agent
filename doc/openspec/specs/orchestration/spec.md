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
交接 SHALL 使用统一执行框架：调度器、beast、pet 三条执行路径 SHALL 复用同一份
`TaskHandoff` 渲染与执行实现；`task` / `context_pack` / `acceptance` / `deadline` /
`priority` / `session_id` 六个字段 SHALL 全部被消费。

`context_pack` SHALL 由交接前置信息构建且**有界**：总预算按粗略 token 估算（CJK 感知），
单字段另有字符上界；预算耗尽时 SHALL 停止装入后续依赖，SHALL NOT 无界拼接。

`deadline` 语义为**秒为单位的时长**（`None` 或 `<=0` = 不设限）；设限时 SHALL 在超时后
取消子 Agent 执行流，并把该子任务归一为失败（错误码 `SUBTASK_TIMEOUT`），SHALL NOT
让任务无限挂起。`session_id` SHALL 原样转交子 Agent 执行（空串 = 未归属），
会话命名空间隔离语义 SHALL 保持不变。

#### Scenario: 能力匹配与交接
- **GIVEN** 一个子任务需要特定能力
- **WHEN** 路由器匹配到合适的子 Agent
- **THEN** 通过 TaskHandoff 交接，交接上下文由 context 模块打包

#### Scenario: 无匹配 Agent
- **GIVEN** 没有子 Agent 能处理当前子任务，且无可用 fallback
- **WHEN** 路由器打分无命中
- **THEN** 抛出 NO_AGENT_MATCH，调度器捕获并标记子任务失败

#### Scenario: 交接全字段被消费
- **GIVEN** 调度器执行一个带依赖、验收标准、优先级与会话标识的子任务
- **WHEN** 子 Agent 收到交接
- **THEN** 执行输入包含原始目标、前置子任务结果与验收标准；TaskHandoff 携带的
  deadline / priority / session_id 与子任务一致

#### Scenario: 交接上下文有界
- **GIVEN** 前置子任务结果总长超过上下文预算
- **WHEN** 构建 context_pack
- **THEN** 包内文本按依赖顺序装入并在预算耗尽处截断，单字段不超过字符上界，
  不会无界拼接全部结果

#### Scenario: 交接超时归一为失败
- **GIVEN** 子任务的 deadline 已设且子 Agent 执行超过该时长
- **WHEN** 执行流被超时取消
- **THEN** 该子任务以 `SUBTASK_TIMEOUT` 失败并进入既有恢复回路，任务不无限挂起

#### Scenario: 三条执行路径复用统一执行器
- **GIVEN** beast / pet 的交接上下文为空且未设验收标准
- **WHEN** 经统一执行器执行
- **THEN** 子 Agent 收到的 prompt 与交接前的任务文本逐字相同，会话标识与执行单元不变

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
系统 SHALL 用 Goal 与 SuccessCriteria 定义任务级成功标准，并由 ProgressTracker 追踪每子任务
进度与整体目标推进，进度未达标时触发重试或重规划。

成功标准 SHALL 默认由拆解器在拆解时生成（顶层 `success_criteria`，2-5 条、每条可客观判定
真伪、覆盖整体目标而不复述子任务 acceptance）；调用方显式提供的非空标准 SHALL 优先于生成
标准；拆解失败回落的单子任务计划 SHALL NOT 自带标准（同源判定 fail-closed 不得把任务拖死）。
重新拆解时原标准非空 SHALL 保留。

任务终态 SHALL 由任务级判定器对照 Goal + SuccessCriteria + 子任务结果判定；未注入判定器而
存在标准时 SHALL 以 `MISSING_SUCCESS_CHECKER` 失败（fail-fast）；判定器异常或返回非法结果
SHALL fail-closed（判未达标），SHALL NOT 裸崩或静默放行。未达标 SHALL 进入恢复回路：重拆
预算未用尽则重新拆解，否则任务判 `FAILED`。

ProgressTracker SHALL 维护每子任务的三态进度：已开始（`started`）、已完成（`completed`）、
失败待恢复（`failed`）；重试开始与完成 SHALL 清除失败标记，重新拆解 SHALL 清空三态。

#### Scenario: 成功标准定义
- **GIVEN** 任务进入拆解且调用方未显式提供成功标准
- **WHEN** planner 产出拆解结果
- **THEN** 计划的 success_criteria 取自 planner 生成的标准（去空白、去重、至多 5 条），
  标准可判定真伪、可度量（SMART）

#### Scenario: 显式标准优先与回落无标准
- **GIVEN** 调用方显式提供了非空成功标准，或 planner 调用失败回落为单子任务
- **WHEN** 拆解完成
- **THEN** 显式标准 SHALL 覆盖生成标准；回落的单子任务计划不带生成标准

#### Scenario: 进度追踪
- **GIVEN** 任务执行中
- **WHEN** 子任务开始、失败、重试
- **THEN** ProgressTracker 的 started / completed / failed 计数随之更新并反映整体目标推进

#### Scenario: 任务级判定
- **GIVEN** 全部子任务通过验收且计划带有成功标准
- **WHEN** 任务进入 VERIFYING
- **THEN** 判定器接收 Goal、成功标准与子任务结果，判定通过才判 `DONE`

#### Scenario: 未达标重试/重规划
- **GIVEN** 子任务进度未达标或任务级判定未通过
- **WHEN** 进度监控检测到偏差
- **THEN** 触发重新拆解（预算未用尽）或判 `FAILED`，衔接状态机 RECOVERING

#### Scenario: 判定器异常 fail-closed
- **GIVEN** 任务级判定器抛出异常或返回非法结果
- **WHEN** 任务进入 VERIFYING
- **THEN** 判定按未达标处理并进入恢复回路，任务不裸崩、不静默判 `DONE`

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

### Requirement: 文件型检查点实现

系统 SHALL 提供满足既有 `CheckpointFn` 协议的**文件型检查点**实现（`FileCheckpoint`）：
每次调用 SHALL 将 `task_id` / `session_id` / `plan`（`plan_to_dict` 形态）/ 已完成子任务 id
与结果写入**单个 JSON 文件**；写入 SHALL 原子（同目录临时文件 + `os.replace`），SHALL NOT
留下半写文件。路径 SHALL 可配置，缺省 `.core/scheduler-checkpoint.json`。实现 SHALL 可被上层
注入的检查点回调**覆盖**（`TaskScheduler(checkpoint=...)` 语义不变）；未显式传入
`FileCheckpoint` 时调度器 SHALL NOT 自行落盘（缺省行为逐字不变）。检查点内容 SHALL NOT 含
密钥（沿用记忆写入前的脱敏约束）。

#### Scenario: 文件型检查点原子落盘
- **GIVEN** 调度器注入了 `FileCheckpoint` 且一个波次收拢
- **WHEN** 检查点回调触发
- **THEN** 单个 JSON 文件包含任务标识、会话标识、计划与已完成结果，文件可被完整解析

#### Scenario: 文件型检查点可恢复
- **GIVEN** 已落盘的检查点文件
- **WHEN** 读取并重建计划
- **THEN** 计划字段（含成功标准 / 重新拆解计数）与已完成子任务结果可还原

#### Scenario: 上层注入覆盖文件型实现
- **GIVEN** 调用方显式传入其他检查点回调
- **WHEN** 调度器触发检查点
- **THEN** 只调用注入回调，`FileCheckpoint` 不参与（不产生文件 I/O）

### Requirement: 运行中取消与消费方断流

系统 SHALL 让运行中任务的取消**打断在途执行**：`cancel(task_id)` SHALL 置取消信号并取消当前
波次的扇出执行单元，SHALL NOT 等待在途子任务自然完成；执行流 SHALL 以 `task_failed`
（错误码 `TASK_CANCELLED`）终止，任务状态 SHALL 进入 `FAILED`，进度上下文 SHALL 释放，
已持久化的断点上下文沿用既有策略保留。对已处于终态（`DONE` / `FAILED`）的任务重复取消
SHALL 幂等（不抛 `INVALID_TRANSITION`）。

消费方在任务流未达终态前断开（停止消费 / 关闭事件流 / 取消消费任务）时，调度器 SHALL
取消在途扇出执行单元并释放任务级上下文，SHALL NOT 遗留后台子任务继续执行；未达终态的任务
SHALL 转入 `FAILED`，SHALL NOT 伪装为成功。

任务到达任一终态后，调度器 SHALL 释放任务级结果缓存与取消信号登记。

#### Scenario: 取消打断在途子任务
- **GIVEN** 任务运行中，一个子任务仍在执行且尚未返回
- **WHEN** 调用 `cancel(task_id)`
- **THEN** 在途子任务被取消，执行流以 `task_failed`（`TASK_CANCELLED`）终止，任务状态为
  `FAILED`，且不等待该子任务自然完成

#### Scenario: 消费方断流释放执行单元
- **GIVEN** 任务流已发出部分事件且子任务仍在执行
- **WHEN** 消费方关闭事件流（不再消费）
- **THEN** 在途子任务被取消，任务转入 `FAILED`，任务级结果缓存被清空，无后台任务继续执行

#### Scenario: 终态清理任务级缓存
- **GIVEN** 任务已到达 `DONE` 或 `FAILED`
- **WHEN** 执行流结束
- **THEN** 任务级结果缓存与取消信号登记被释放

#### Scenario: 重复取消终态任务幂等
- **GIVEN** 任务已处于 `FAILED`（或 `DONE`）
- **WHEN** 再次调用 `cancel(task_id)`
- **THEN** 不抛 `INVALID_TRANSITION`，任务保持原终态

### Requirement: 后台委托与完成通知

系统 SHALL 支持**后台委托**：`tools.delegate` 接受可选参数 `background`（缺省 `false`）；
为 `true` 时 SHALL 立即返回 `task_id` 与 `running` 状态，SHALL NOT 阻塞主循环等待子 Agent。
为 `false`（或省略）时既有阻塞委托语义 SHALL 逐字不变。

后台委托 SHALL 有界：运行中的后台任务上限 SHALL 为 8；超限 SHALL 以结构化失败返回
（`ok=false`），SHALL NOT 排队或静默丢弃。每个后台任务 SHALL 落在
`running → done | failed | cancelled` 之一，终态 SHALL 不可变。

完成通知 SHALL 按**会话**记录，并在该会话**下一轮轮首**一次性投递（取走后清除）；
通知 SHALL 有界（每会话待投递 ≤ 32 条，超出丢弃最旧）。系统 SHALL 提供模型侧只读任务
清单（`tools.tasks` 的 `list` / `status`），SHALL NOT 因查询而清空通知。

子 Agent 的工具面 SHALL 继续不含 `tools.delegate` 与 `tools.tasks`（结构上不可再委托、
不可跨 Agent 查看清单）。

#### Scenario: 后台委托立即返回

- **GIVEN** 一个可匹配的子 Agent 且运行中后台任务未达上限
- **WHEN** 模型调用 `tools.delegate(task=..., background=true)`
- **THEN** 工具结果 SHALL 立即返回 `{ok: true, task_id, agent, status: "running"}`
- **AND THEN** 子 Agent 仍在后台执行，主循环 SHALL NOT 等待其完成

#### Scenario: 缺省阻塞语义不变

- **GIVEN** 调用未带 `background`（或显式 `false`）
- **WHEN** 主循环发起委托
- **THEN** 工具 SHALL 等待子 Agent 完成并回传 reply，与引入后台能力前逐字一致

#### Scenario: 完成后通知在下一轮投递且只投一次

- **GIVEN** 某个后台任务已完成（done / failed / cancelled）
- **WHEN** 该会话下一轮开始
- **THEN** 通知 SHALL 以独立块注入模型上下文，含 task_id / agent / 状态 / 有界摘要
- **AND THEN** 再次开始一轮 SHALL NOT 重复投递同一通知

#### Scenario: 通知按会话隔离

- **GIVEN** 会话 A 与会话 B 各有后台任务
- **WHEN** 会话 A 的下一轮开始
- **THEN** SHALL ONLY 投递 A 的通知，B 的通知 SHALL 保持待投递

#### Scenario: 后台任务有界

- **GIVEN** 运行中的后台任务已达上限 8
- **WHEN** 再发起一个后台委托
- **THEN** 工具 SHALL 返回结构化失败（`ok=false`），SHALL NOT 启动第 9 个任务

#### Scenario: 任务清单只读可查

- **GIVEN** 本进程曾发起后台委托
- **WHEN** 模型调用 `tools.tasks` 的 `list` 或 `status`
- **THEN** SHALL 返回任务状态与有界结果摘要；未知 `task_id` SHALL 返回 `found=false`；
  该调用 SHALL NOT 清空待投递通知

#### Scenario: 子 Agent 不可窥视或再委托

- **GIVEN** 子 Agent 独立 loop 的工具面
- **WHEN** 检查其工具清单
- **THEN** SHALL NOT 含 `tools.delegate` 或 `tools.tasks`

### Requirement: 未完成任务自动续跑

系统 SHALL 提供**显式开启**的未完成任务自动续跑：配置 `orchestration.auto_resume`
（默认 `false`）开启后，`core-agent task` 启动路径 SHALL 扫描检查点，对未完成
（`done=false`）的编排任务重建计划 / 已完成子任务集 / 交接结果 / 发起会话标识并续跑。

- 自动续跑 SHALL 跳过：已完成（`done=true`）任务、会话轮级检查点（`task_id` 以 `turn.` 开头
  或状态标记 `kind=turn`）、以及缺少可解析计划或快照损坏者（降级跳过并告警，
  SHALL NOT 中断其余任务）。
- 自动续跑 SHALL **有界**：同一任务跨进程最多 **3** 次自动尝试；两次尝试间 SHALL 指数退避
  （首次尝试后 60s、随后每次翻倍，上限 `3600s`），计数与时间戳 SHALL 持久化于状态目录
  （`auto-resume.json`，`0600`，不含任务正文 / 记忆 / 密钥）。达到上限 SHALL 跳过并告警，
  SHALL NOT 删除检查点；人工 `task --resume <id>` SHALL 不受该上限与退避约束。
- 续跑失败 SHALL 保留检查点，使下次启动可在退避后重试。
- `auto_resume=false` 时启动路径 SHALL 维持既有「纯扫描 + 呈现」语义，SHALL NOT 自动重执行。
- `core-agent task --resume-all` SHALL 作为显式入口续跑全部未完成任务，SHALL 不受配置开关与
  退避 / 上限约束。

#### Scenario: 默认关闭只呈现
- **GIVEN** `orchestration.auto_resume=false` 且存在未完成编排任务
- **WHEN** 执行 `core-agent task <新目标>`
- **THEN** 只呈现「未完成任务 / `task --resume <id>`」提示，不自动续跑，且新目标照常执行

#### Scenario: 开启后自动续跑
- **GIVEN** `auto_resume=true`，检查点含未完成任务（计划 / 已完成子任务 / 交接结果 / 会话标识）
- **WHEN** 执行 `core-agent task <新目标>`
- **THEN** 先按检查点重建并续跑未完成任务，已完成子任务不重复执行，再执行新目标

#### Scenario: 跳过不可续跑项
- **GIVEN** 检查点分别属于已完成任务、会话轮级检查点、以及无计划的坏快照
- **WHEN** 自动续跑扫描
- **THEN** 三类均不被续跑；坏快照降级告警且不影响其余任务

#### Scenario: 自动尝试有界
- **GIVEN** 同一未完成任务已自动尝试 3 次且仍失败
- **WHEN** 再次启动
- **THEN** 该任务被跳过并告警，检查点保留；人工 `task --resume <id>` 仍可执行

### Requirement: 后台任务跨重启登记与重入队

系统 SHALL 把后台子 Agent 任务的元数据**持久化**于状态目录
（`background-tasks.json`，`0600`、原子替换），字段 SHALL 限于
`task_id / agent_id / task / status / started_at / finished_at / session_id / error /
owner_pid / owner_start`；`task` 与 `error` SHALL 经密钥形态脱敏并有界。`owner_pid` SHALL
为启动该任务的进程 pid，`owner_start` SHALL 为该进程的启动标识（平台可取得时非空）。
`owner_pid / owner_start` SHALL NOT 对模型暴露。登记 SHALL 有界（最多保留最新 64 条），
文件损坏 SHALL 告警后按空登记处理，SHALL NOT 阻断启动或主循环。

重启加载时，落盘状态为 `running` 的任务 SHALL 按 owner 存活情况处理：owner 已退出、
owner 信息缺失（旧格式）或 pid 存活但启动标识不符（pid 复用）时，SHALL 映射为终态
`interrupted`（`error` 标记「进程重启导致中断」）；owner 仍存活时，SHALL 保持 `running`，
SHALL NOT 映射为 `interrupted`，SHALL NOT 由本进程取消或接管，也 SHALL NOT 重放完成通知
（该任务 SHALL 可由 `tools.tasks` 查询；`tools.task_retry` 按 running 规则拒绝）。
`interrupted` SHALL NOT 占用运行中上限。

登记写入 SHALL 在短独占建议锁内完成（同目录 `.{文件名}.lock`，POSIX `flock` / Windows
`msvcrt.locking`），并 SHALL 在锁内重新读取磁盘登记后**合并**写入：本实例变更过的条目
覆盖磁盘版本，未变更条目 SHALL 保留磁盘版本 —— 并发进程的登记与更新 SHALL NOT 被覆盖或
回滚；取锁失败 SHALL 降级为直接写入，SHALL NOT 阻断任务。写侧 SHALL 仍按 `started_at`
保留最新 64 条。

系统 SHALL 提供模型侧重入队工具 `tools.task_retry`：对 `interrupted / failed / cancelled`
任务，按登记的任务正文重新匹配子 Agent 并启动新的后台任务，返回新 `task_id`；
对 `running`（仍在执行）与 `done`（已完成）SHALL 结构化拒绝（`ok=false`）。
重入队 SHALL 恢复原会话归属；达到运行中上限时 SHALL 返回结构化失败。
`tools.task_retry` SHALL 判 `HIGH_RISK`（需人工审批），coeffect SHALL 为 `task:write`，
且 SHALL 只挂主工具面 —— 子 Agent SHALL NOT 可见。

#### Scenario: 终态跨重启可见

- **GIVEN** 一个后台任务已落终态（done / failed / cancelled）且登记已落盘
- **WHEN** 新进程构造注册表
- **THEN** `tools.tasks` SHALL 返回该任务及其终态，任务正文与错误 SHALL 有界且已脱敏

#### Scenario: 重启把运行中任务标记为被中断

- **GIVEN** 登记文件中存在 `status=running` 的任务，其 owner 进程已退出或 owner 信息缺失
- **WHEN** 新进程构造注册表
- **THEN** 该任务状态 SHALL 为 `interrupted`，`finished_at` SHALL 保持空
- **AND THEN** 系统 SHALL NOT 自动重执行该任务，SHALL NOT 投递完成通知

#### Scenario: 存活 owner 的在途任务不被误标

- **GIVEN** 登记文件中存在 `status=running` 的任务，其 `owner_pid` 存活且 `owner_start` 一致
- **WHEN** 另一进程构造注册表
- **THEN** 该任务状态 SHALL 保持 `running`，`finished_at` SHALL 保持空
- **AND THEN** SHALL NOT 投递完成通知，SHALL NOT 由本进程取消；`tools.task_retry` SHALL
  按 running 拒绝

#### Scenario: pid 复用不被误判为存活

- **GIVEN** 登记文件中存在 `status=running` 的任务，其 `owner_pid` 对应当前存活进程但
  `owner_start` 与当前进程启动标识不一致
- **WHEN** 构造注册表
- **THEN** 该任务 SHALL 映射为 `interrupted`（不把复用 pid 的无关进程当作 owner）

#### Scenario: 并发写不丢登记且不回滚新状态

- **GIVEN** 两个注册表实例共享同一状态文件，实例 B 已加载；随后实例 A 新增或更新了条目
- **WHEN** 实例 B 写入自己的条目
- **THEN** A 写入的条目与更新 SHALL 保留在状态文件中（不被 B 的陈旧快照覆盖）
- **AND THEN** 写侧 SHALL 在锁内按 `started_at` 保留最新至多 64 条

#### Scenario: 重入队被中断的任务

- **GIVEN** 一个 `interrupted`（或 `failed` / `cancelled`）的后台任务且存在可匹配子 Agent
- **WHEN** 模型调用 `tools.task_retry(task_id=...)` 并通过审批
- **THEN** 工具 SHALL 启动新的后台任务并返回新 `task_id` 与 `status="running"`
- **AND THEN** 原任务终态 SHALL 保持不变

#### Scenario: 运行中或已完成的任务拒绝重入队

- **GIVEN** 目标任务状态为 `running` 或 `done`
- **WHEN** 模型调用 `tools.task_retry`
- **THEN** 工具 SHALL 返回 `ok=false`，SHALL NOT 启动新任务

#### Scenario: 登记有界且损坏容忍

- **GIVEN** 登记文件损坏（坏 JSON / 结构不符）
- **WHEN** 新进程构造注册表
- **THEN** SHALL 告警一次并按空登记处理，启动 SHALL 继续
- **AND THEN** 登记条目数 SHALL 不超过 64 条（超出淘汰最旧）

#### Scenario: 登记不含密钥明文

- **GIVEN** 委托任务正文含密钥形态子串
- **WHEN** 登记落盘
- **THEN** 状态文件中 SHALL NOT 出现该密钥明文

### Requirement: 整任务时限与 token 预算

系统 SHALL 为无人值守任务提供整任务级护栏，两项均缺省关闭（`0`）：

- **墙钟时限** `orchestration.task_timeout`：`task` 入口（新任务、`--resume`、自动续跑与
  `--resume-all` 的逐任务执行）SHALL 以整任务流为范围施加时限（含拆解、全部波次与任务级
  判定）。超时 SHALL 终止任务流，SHALL 保留最近一次波次检查点（可由 `--resume` 续跑），
  SHALL 以非零退出码收口，并 SHALL 产生 `TASK_TIMEOUT` 失败通知（若配置了通知 sink）。
  `0` SHALL 表示不设限，行为与引入前逐字一致。
- **token 预算** `orchestration.task_token_budget`：调度器 SHALL 按任务累计各子任务执行返回的
  `LoopResult.token_used`（子循环收尾时的上下文记账估算）。累计值达到或超过正预算时，
  系统 SHALL 以 `TASK_TOKEN_BUDGET_EXCEEDED` 终止任务（`task_failed`），SHALL NOT 对越界
  子任务重试，SHALL NOT 重新拆解，任务状态 SHALL 为 `FAILED`；终态载荷 SHALL 携带
  `token_used` 与 `token_budget`。`0` SHALL 表示关闭预算，累计 SHALL NOT 影响任务结局。
  任务级累计 SHALL 在该任务任意终态/断流/取消退出时清除。

#### Scenario: 整任务超时终止

- **GIVEN** `orchestration.task_timeout=30` 且任务在 30 秒内未完成
- **WHEN** 时限到达
- **THEN** 任务流 SHALL 被取消，入口 SHALL 打印超时信息并以退出码 1 收口
- **AND THEN** 最近一次波次检查点 SHALL 保留；配置了通知 sink 时 SHALL 写入 `TASK_TIMEOUT`

#### Scenario: 时限为 0 不设限

- **GIVEN** `orchestration.task_timeout=0`
- **WHEN** 执行任意长任务
- **THEN** 系统 SHALL NOT 施加整任务时限（与引入前一致）

#### Scenario: token 预算耗尽即失败且不恢复

- **GIVEN** `orchestration.task_token_budget` 为正数，且累计 `LoopResult.token_used`
  达到该值
- **WHEN** 当前子任务执行完成
- **THEN** 任务 SHALL 以 `task_failed`（`TASK_TOKEN_BUDGET_EXCEEDED`）终止
- **AND THEN** 系统 SHALL NOT 重试该子任务、SHALL NOT 重新拆解计划

#### Scenario: 预算为 0 关闭

- **GIVEN** `orchestration.task_token_budget=0`
- **WHEN** 子任务报告的 `token_used` 任意大
- **THEN** 任务 SHALL 按既有验收/恢复语义推进，预算 SHALL NOT 改变结局

#### Scenario: 累计在终态后清除

- **GIVEN** 一个任务已到达终态（完成 / 失败 / 取消 / 断流）
- **WHEN** 同一调度器执行下一个任务
- **THEN** 新任务的 token 累计 SHALL 从 0 开始

### Requirement: 任务失败通知 sink

系统 SHALL 支持 `orchestration.failure_notify_file` 指定的本地 JSONL 通知文件（缺省空 =
关闭）。任务终态失败时 SHALL 追加**一行** JSON，字段 SHALL 包含
`ts / event / task_id / session_id / code / reason / goal`；`reason` 与 `goal` SHALL 经密钥
形态脱敏并截断（500 字符）。文件不存在时 SHALL 以 `0600` 创建（父目录按需创建）。
用户主动取消（`TASK_CANCELLED`）SHALL NOT 产生通知。写入失败 SHALL 只在 stderr 告警，
SHALL NOT 改变任务结局或退出码。通知 sink SHALL 覆盖入口超时（`TASK_TIMEOUT`）与自动续跑
失败；`serve` / TUI 等非 `task` 入口不在本要求范围内。

系统 SHALL 另支持 `orchestration.failure_notify_webhook` 指定的 HTTP(S) 远程 sink（缺省空 =
关闭）。启用时 SHALL 在任务失败收口以 `POST`、`Content-Type: application/json` 发送一份
JSON，字段 SHALL 包含 `text / event / task_id / session_id / code / reason / goal`；
`reason` 与 `goal` SHALL 经同一脱敏与截断。请求 SHALL 有界（5 秒）且为单次尝试；
失败 SHALL 只在 stderr 告警（SHALL NOT 回显 URL），SHALL NOT 改变任务结局或退出码。
两个 sink SHALL 相互独立：任一失败 SHALL NOT 阻止另一个写入。取消语义与文件 sink 相同。

#### Scenario: 失败追加一行 JSON

- **GIVEN** 配置了通知文件且任务以失败终态结束
- **WHEN** 任务收口
- **THEN** 文件 SHALL 追加一行 JSONL，含 `task_id / code / reason / ts`
- **AND THEN** 再次失败 SHALL 追加第二行（不覆盖历史）

#### Scenario: 通知正文脱敏

- **GIVEN** 失败原因或任务目标含密钥形态子串
- **WHEN** 写入通知
- **THEN** 文件中 SHALL NOT 出现密钥明文（以 `<redacted>` 代替）
- **AND THEN** 启用了 webhook 时请求体 SHALL 同样不含密钥明文

#### Scenario: 未配置不落盘

- **GIVEN** `orchestration.failure_notify_file` 为空
- **WHEN** 任务失败
- **THEN** 系统 SHALL NOT 创建或写入任何通知文件

#### Scenario: 主动取消不通知

- **GIVEN** 配置了通知文件且任务被用户取消（`TASK_CANCELLED`）
- **WHEN** 任务收口
- **THEN** 系统 SHALL NOT 写入通知，SHALL NOT 发起 webhook 请求

#### Scenario: 写入失败不影响任务结局

- **GIVEN** 通知路径不可写（如父路径为普通文件）
- **WHEN** 任务失败并尝试写通知
- **THEN** stderr SHALL 告警，任务失败结局与退出码 SHALL 保持不变

#### Scenario: webhook 推送失败不影响任务结局

- **GIVEN** 配置了 webhook 且接收端不可用（连接失败 / 超时 / 非 2xx）
- **WHEN** 任务失败并尝试推送
- **THEN** stderr SHALL 告警且不含 URL 值，任务结局与退出码 SHALL 保持不变
- **AND THEN** 若同时配置了通知文件，文件 SHALL 已正常写入

#### Scenario: 未配置 webhook 不发起请求

- **GIVEN** `orchestration.failure_notify_webhook` 为空
- **WHEN** 任务失败
- **THEN** 系统 SHALL NOT 发起任何网络请求

### Requirement: 子 Agent 工作树隔离

配置 `orchestration.worktree_isolation` 为 false（缺省）时，委托路径 SHALL 与引入前逐字一致：
不创建工作树、不改变工具面、结果形状、完成通知与持久化字段。开启时，每次 `tools.delegate`
（前台与后台）SHALL 在宿主仓库的独立 git worktree 中运行，分支 SHALL 为
`core-agent/wt-<id>`，路径 SHALL 位于状态目录的 `worktrees/<repo_key>/<worktree_id>/` 下。

工作树 SHALL 基于仓库 `HEAD` 创建；主工作区未提交的改动 SHALL NOT 进入子 Agent 工作树。
子 Agent 使用 `tools.file_read` / `tools.file_write` / `tools.file_patch` 的**相对路径**时，
SHALL 解析到工作树根；`tools.code_run` 省略 `cwd` 时 SHALL 以工作树根为工作目录，显式相对
`cwd` SHALL 相对工作树根解析。绝对路径、`~` 展开结果与符号链接目标 SHALL 保持原语义 ——
本隔离是路径作用域，SHALL NOT 被表述或实现为安全沙箱。

创建 SHALL 在子 Agent 开始前完成，并在以下任一情况 fail-closed 返回结构化错误码
`WORKTREE_UNAVAILABLE`，SHALL NOT 回退到主工作区运行：当前目录不是 git 仓库；仓库没有可
解析的 `HEAD`；状态目录位于仓库内；目标工作树目录已存在；git 命令失败。错误信息 SHALL NOT
回显 git stderr。

任务进入终态（`done / failed / cancelled / interrupted`）后，工作树与分支 SHALL 保留；
系统 SHALL NOT 自动合并、自动提交、自动删除或自动 prune。前台委托结果与后台任务登记 SHALL
携带工作树元数据（`id / path / branch / repo_root / changed_files`），后台完成通知 SHALL 携带
工作树 id（不携带路径）；元数据 SHALL 跨重启保留并可由 `tools.tasks` 查询。

系统 SHALL 在主工具面提供两个工作树工具，子 Agent 工具面 SHALL NOT 包含它们：

- `tools.worktree.list`：只读清单，判 `READ`，coeffect `worktree:read`；返回工作树 id、
  分支、路径、仓库根、agent 与存在性，最多 50 条并报告是否截断（不触发 git 扫描）。
- `tools.worktree.discard`：按 `worktree_id` 显式丢弃，判 `HIGH_RISK`（需人工审批），
  coeffect `worktree:write`，不可逆；SHALL 拒绝正在运行的后台任务所占用的工作树；SHALL
  拒绝登记被篡改、路径越出状态根或分支名不符的记录；`force=false` 时 SHALL 拒绝含未提交
  改动的工作树并提示改用 `force=true`；对不存在或已丢弃的 id SHALL 幂等返回成功且不报错。

工作树 sidecar 登记 SHALL 为 `0600` 原子写，字段 SHALL 限于
`version / id / repo_root / path / branch / agent_id / created_at`，SHALL NOT 包含任务正文、
会话标识或回复内容。状态目录与工作树根 SHALL 为 `0700`（平台不支持时尽力而为）。

#### Scenario: 开关关闭时行为不变

- **GIVEN** `orchestration.worktree_isolation` 未配置或为 false
- **WHEN** 执行前台或后台 `tools.delegate`
- **THEN** 不创建工作树，不注册工作树工具
- **AND THEN** 前台结果仍为 `{ok, reply}`，后台结果仍为 `{ok, task_id, status, agent}`，
  通知与登记文件不新增字段

#### Scenario: 前台子 Agent 的文件写入被隔离

- **GIVEN** 隔离已开启，主仓库位于某个 git 仓库
- **WHEN** 前台子 Agent 以相对路径写入文件
- **THEN** 文件 SHALL 只出现在该子 Agent 的工作树中，主工作区 `git status` SHALL 保持干净
- **AND THEN** 前台结果 SHALL 含工作树 id、路径、分支与非空 `changed_files`

#### Scenario: code_run 缺省工作目录为工作树

- **GIVEN** 隔离已开启
- **WHEN** 子 Agent 执行省略 `cwd` 的 `tools.code_run`
- **THEN** 命令的工作目录 SHALL 为该子 Agent 的工作树根
- **AND THEN** 显式相对 `cwd` 亦 SHALL 相对工作树根解析

#### Scenario: 绝对路径不受工作区约束

- **GIVEN** 隔离已开启
- **WHEN** 子 Agent 使用绝对路径写入主工作区中的文件
- **THEN** 写入 SHALL 落在该绝对路径（主工作区文件被修改）
- **AND THEN** 系统 SHALL NOT 将其重映射到工作树（隔离不是安全沙箱）

#### Scenario: 非 git 仓库 fail-closed

- **GIVEN** 隔离已开启且当前目录不是 git 仓库（或仓库无提交）
- **WHEN** 执行 `tools.delegate`
- **THEN** 委托 SHALL 返回 `ok=false` 与 `WORKTREE_UNAVAILABLE`
- **AND THEN** 子 Agent SHALL NOT 被调用，SHALL NOT 创建任何工作树或 sidecar

#### Scenario: 后台任务隔离且可跨重启查询

- **GIVEN** 隔离已开启
- **WHEN** 后台子 Agent 以相对路径写入文件
- **THEN** 文件 SHALL 落在其工作树，主工作区不变
- **AND THEN** `tools.tasks` SHALL 显示工作树 id/path/branch，完成通知 SHALL 含工作树 id；
  新进程加载登记后 SHALL 仍能查询该元数据

#### Scenario: 终态保留与重入队新工作树

- **GIVEN** 一个后台任务已进入终态（done / failed / cancelled）
- **WHEN** 检查工作树并对其调用 `tools.task_retry`
- **THEN** 原工作树、分支与 sidecar SHALL 保留
- **AND THEN** 重入队 SHALL 创建新的工作树与分支，旧工作树 SHALL NOT 被复用或删除

#### Scenario: 显式丢弃

- **GIVEN** 一个已保留的工作树
- **WHEN** 调用 `tools.worktree.discard`
- **THEN** 工作树目录、分支与 sidecar SHALL 被删除
- **AND THEN** 对同一 id 再次调用 SHALL 幂等返回成功且不报错

#### Scenario: 拒绝运行中任务与越界登记

- **GIVEN** 工作树被一个 running 后台任务占用，或 sidecar 的路径/分支被篡改
- **WHEN** 调用 `tools.worktree.discard`
- **THEN** SHALL 返回 `ok=false` 且不删除任何工作树或外部路径
- **AND THEN** 未提供 `force=true` 时，含未提交改动的工作树亦 SHALL 被拒绝

#### Scenario: 子 Agent 工具面不可见

- **GIVEN** 隔离已开启
- **WHEN** 检查各子 Agent 的工具面
- **THEN** SHALL NOT 含 `tools.worktree.list` 或 `tools.worktree.discard`
- **AND THEN** 两个工具 SHALL 仅在主工具面注册

### Requirement: 续跑批次单实例互斥

系统 SHALL 在扫描未完成编排任务**之前**获取以 `$CORE_STATE_DIR` 为作用域的非阻塞独占锁，
并使锁覆盖整个续跑批次（扫描、逐任务执行与自动续跑状态读写的全过程）。锁 SHALL 使用平台
原生建议锁（POSIX `flock` / Windows `msvcrt.locking`）；锁文件 SHALL 为
`$CORE_STATE_DIR/.auto-resume.json.lock`，SHALL 以 `0600` 创建（平台不支持时为尽力而为），
且 SHALL NOT 在释放时删除。

同一 `$CORE_STATE_DIR` 下已有进程持有该锁时，新的续跑批次 SHALL 立即跳过：SHALL NOT
扫描检查点、SHALL NOT 执行任何任务、SHALL NOT 写自动续跑状态。`core-agent task --resume-all`
SHALL 向 stderr 输出可检索前缀 `[resume_skipped]` 并以退出码 0 结束。
`orchestration.auto_resume=true` 时，锁被占用 SHALL NOT 阻止新任务：自动续跑 SHALL 被跳过，
`task <目标>` SHALL 照常执行新目标。

进程终止（含崩溃）后 SHALL 不再持有该锁（由操作系统释放）；锁文件残留 SHALL NOT 阻止
后续批次。创建锁文件或取锁失败时系统 SHALL fail-closed（跳过续跑），SHALL NOT 降级为
无锁续跑；此时 `task --resume-all` SHALL 输出 `[resume_skipped]` 并以非零退出码结束，
`orchestration.auto_resume=true` 的 `task <目标>` SHALL 仅跳过续跑并照常执行新目标。

不同 `$CORE_STATE_DIR` 的批次 SHALL 互不影响。该锁 SHALL 只串行化**续跑批次**；
`task <目标>`（未开启自动续跑时）、`task --resume <id>`、REPL、后台与 `serve` 路径
SHALL NOT 受其约束，且系统 SHALL NOT 声称检查点文件因此获得跨进程单写者一致性。

#### Scenario: 重叠续跑被跳过且退出码为 0

- **GIVEN** 另一进程持有 `.auto-resume.json.lock`
- **WHEN** 执行 `core-agent task --resume-all`
- **THEN** 不扫描检查点、不执行任务、不写自动续跑状态
- **AND THEN** stderr SHALL 含 `[resume_skipped]`，退出码 SHALL 为 0

#### Scenario: 锁覆盖任务执行阶段

- **GIVEN** 一个续跑批次已取锁并正在执行某个任务
- **WHEN** 同一状态目录下启动第二个 `task --resume-all`
- **THEN** 第二个实例 SHALL 立即跳过，SHALL NOT 执行任何任务
- **AND THEN** 第一个批次 SHALL 继续持有锁直到批次结束

#### Scenario: 锁释放后可继续续跑

- **GIVEN** 上一次批次已结束，或持有锁的进程已终止（含崩溃）
- **WHEN** 执行下一次 `core-agent task --resume-all`
- **THEN** SHALL 获得锁并正常扫描、续跑
- **AND THEN** 残留的锁文件 SHALL NOT 阻止执行

#### Scenario: 自动续跑锁忙不阻塞新任务

- **GIVEN** `orchestration.auto_resume=true` 且另一进程持有续跑批次锁
- **WHEN** 执行 `core-agent task <新目标>`
- **THEN** 自动续跑 SHALL 被跳过并输出 `[resume_skipped]`
- **AND THEN** 新目标 SHALL 照常执行，退出码 SHALL 为 0

#### Scenario: 锁作用域与权限

- **GIVEN** 两个不同的 `$CORE_STATE_DIR`
- **WHEN** 两个进程各自执行续跑批次
- **THEN** 两者 SHALL 互不阻塞
- **AND THEN** 同一状态目录下的锁文件 SHALL 为 `.auto-resume.json.lock` 且模式为 `0600`

#### Scenario: 取锁失败 fail-closed

- **GIVEN** 状态目录不可创建或锁文件不可打开
- **WHEN** 执行 `core-agent task --resume-all`
- **THEN** SHALL 跳过且不执行任何任务，stderr SHALL 含 `[resume_skipped]`
- **AND THEN** 退出码 SHALL 为非零，且 SHALL NOT 降级为无锁续跑
