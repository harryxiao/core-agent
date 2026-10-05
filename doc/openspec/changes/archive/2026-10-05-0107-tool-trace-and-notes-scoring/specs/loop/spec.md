# Loop Specification Delta

## MODIFIED Requirements

### Requirement: 异步流式执行
系统 SHALL 提供异步执行入口 arun 与流式入口 astream，与同步 run 共用同一执行循环语义；astream 返回 AsyncIterator[LoopEvent]，以 loop_started / action_started / action_completed / step_completed / reply_delta / loop_finished / loop_failed 七类事件流式产出执行生命周期，支持事件循环内非阻塞调用与流式编排；run 保留为薄壳（thin wrapper），内部经事件循环桥接调用对应异步实现，调用方无需感知事件循环、零改动。工具动作事件仅对非终止动作（tool_id 非空）产出：action_started 于工具执行前携带 round/tool_id/args 节选，action_completed 于执行后携带 round/tool_id/ok/duration_ms/output 节选；节选有界（≤400 字符），既有五类事件的节奏与语义不变。除上述**事件流**外，循环 SHALL 在**非终止动作**完成后**另行产出工具调用遥测**（`kind="tool_call"`，载荷含工具 id / 参数 / 成败与耗时，且**有界**），使「按工具 id 归因」的证据在**生产**链路可得（见 evolution「经验采集」①工具调用类）；该产出 SHALL NOT 改变上述 `LoopEvent` 的外发路径、事件序与既有消费语义，未注入 tracer 时 SHALL 不产出（行为与既有缺省一致）。

#### Scenario: 异步执行入口
- **GIVEN** 内核运行于事件循环中，需并发驱动多个执行循环
- **WHEN** 经 arun 发起执行
- **THEN** 调用不阻塞事件循环，返回 awaitable，多个执行循环可并发运行

#### Scenario: 流式事件产出
- **GIVEN** 一个执行循环按"观察→推理→行动→记忆"逐轮推进
- **WHEN** 经 astream 发起流式执行
- **THEN** 返回 AsyncIterator[LoopEvent]，按生命周期顺序产出 loop_started、每轮 step_completed、逐 token reply_delta、终态 loop_finished 或 loop_failed

#### Scenario: 工具动作事件
- **GIVEN** 一轮推理产出非终止动作（tool_id 非空）
- **WHEN** 该动作经 act 执行
- **THEN** 执行前产出 action_started（round/tool_id/args 节选）、执行后产出 action_completed（round/tool_id/ok/duration_ms/output 节选），两者先于该轮 step_completed

#### Scenario: 终止动作不产出动作事件
- **GIVEN** 一轮推理产出终止动作（tool_id 为空，本轮进入回复收尾）
- **WHEN** 该动作经 act 执行
- **THEN** 不产出 action_started / action_completed（终止动作非工具调用）

#### Scenario: 同步薄壳等价
- **GIVEN** 调用方处于同步上下文
- **WHEN** 调用 run 同步入口
- **THEN** 语义与 arun 一致，内部经事件循环桥接（asyncio.run）完成调用，调用方无需改动、无需感知事件循环

#### Scenario: 工具动作产出工具调用遥测
- **GIVEN** 已注入 `tracer`，且一轮推理产出一个非终止动作
- **WHEN** 该动作经 act 执行完成
- **THEN** trace 流新增一条 `kind="tool_call"` 事件（含工具 id / 成败 / 耗时，载荷**有界**），并可由本轮的 trace 完成回调回放——按工具 id 归因的证据链在生产可得

#### Scenario: 终止动作不产出工具调用遥测
- **GIVEN** 一轮推理产出终止动作（tool_id 为空，本轮进入回复收尾）
- **WHEN** 该动作经 act「执行」完成
- **THEN** 不产出 `kind="tool_call"` 遥测（终止动作非工具调用，与 `action_completed` 同判据）

#### Scenario: 未注入 tracer 不产出工具调用遥测
- **GIVEN** 未注入 `tracer` 的一次执行
- **WHEN** 非终止动作经 act 执行完成
- **THEN** 不产出工具调用遥测，本轮回复、事件序与终止语义均与既有缺省一致
