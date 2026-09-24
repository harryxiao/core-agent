任务规划与编排把单一循环升级为可处理长周期复杂任务的执行引擎，提供状态机管理、子任务拆解、多 Agent 协同三层基础能力，并新增并行扇出、目标监控、优先级调度三项运行时能力，确保复杂目标可并行推进、可量化校验、可按优先级调度。（来源：core-agent_gap_analysis.md，2026-09-21）

## ADDED Requirements

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
