
任务规划与编排把单一循环升级为可处理长周期复杂任务的执行引擎，提供状态机管理、子任务拆解、多 Agent 协同三层能力，确保复杂目标可控、可校验、可推进。

## ADDED Requirements

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

