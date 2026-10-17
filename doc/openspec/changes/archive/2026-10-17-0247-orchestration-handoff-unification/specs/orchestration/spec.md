# Delta — change 0247（orchestration R3）

## MODIFIED Requirements

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
