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
系统 SHALL 将大目标拆解为带验收标准的分步子任务，按依赖拓扑序执行，并逐步校验。

#### Scenario: 拆解与拓扑执行
- **GIVEN** 一个复杂目标
- **WHEN** 拆解器生成子任务 DAG
- **THEN** 子任务按依赖拓扑序执行，无依赖项可并行

#### Scenario: LLM 拆解产出子任务 DAG
- **GIVEN** 拆解器注入 LLM planner
- **WHEN** 输入一个复合目标
- **THEN** planner 经模型调用产出子任务 DAG（id/goal/acceptance/depends_on），按依赖拓扑序与波次执行

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

### Requirement: 子任务验收门
系统 SHALL 对带验收标准的子任务结果经 LLM 对照判定（验收门）：判定通过才记录完成并推进；判定不通过或判定器不可用时标记失败不推进（fail-closed）；无验收标准时退化为离线非空判定，不调用模型。

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

### Requirement: 多 Agent 协同
系统 SHALL 支持按任务类型路由到最合适的子 Agent，并通过标准化消息协议完成交接。

#### Scenario: 能力匹配与交接
- **GIVEN** 一个子任务需要特定能力
- **WHEN** 路由器匹配到合适的子 Agent
- **THEN** 通过 TaskHandoff 交接，交接上下文由 context 模块打包

#### Scenario: 无匹配 Agent
- **GIVEN** 没有子 Agent 能处理当前子任务
- **WHEN** 路由器返回无匹配
- **THEN** 降级到备用 Agent 或转人工审批

### Requirement: 断点续跑
系统 SHALL 支持长任务挂起、恢复与取消（断点续跑）：挂起时持久化执行上下文与中间结果，恢复时从断点继续而非重头执行，取消时释放已占用资源。

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

### Requirement: 任务入口与进度事件
系统 SHALL 提供 `core-agent task <目标>` CLI 入口驱动编排器：流式产出任务进度事件（task_started / plan_ready / wave_started / subtask_started / subtask_completed / task_checkpoint / task_finished / task_failed），关键节点（拆解、验收、检查点、终态）写入 trace 审计；支持从检查点断点续跑（重建原计划与已完成子任务集，未完成子任务续跑，已完成子任务不重复执行）。

#### Scenario: CLI 任务入口流式进度
- **GIVEN** 一个复合目标
- **WHEN** 执行 `core-agent task <目标>`
- **THEN** 拆解出子任务 DAG 按依赖序执行，进度事件依序流式输出，验收与检查点写入 trace

#### Scenario: 断点续跑恢复
- **GIVEN** 任务执行中断（进程被杀）且检查点已持久化
- **WHEN** 以同一 task-id 从检查点恢复
- **THEN** 重建原计划并跳过已完成子任务，仅续跑未完成子任务（幂等恢复），已完成子任务结果重建为依赖上下文

#### Scenario: 任务失败可见
- **GIVEN** 某子任务验收失败
- **WHEN** 编排器收拢该波次
- **THEN** 流式产出 task_failed 事件并携带失败子任务与理由，命令以非零退出码结束
