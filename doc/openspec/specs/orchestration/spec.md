# Orchestration Specification

## Purpose
任务规划与编排把单一循环升级为可处理长周期复杂任务的执行引擎，提供状态机管理、子任务拆解、多 Agent 协同三层基础能力，并新增并行扇出、目标监控、优先级调度三项运行时能力，确保复杂目标可并行推进、可量化校验、可按优先级调度。

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

#### Scenario: 子任务校验通过才推进
- **GIVEN** 一个子任务执行完成
- **WHEN** 结果未通过其验收标准
- **THEN** 不推进下一步，回退重试（有限次）或重新规划

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
