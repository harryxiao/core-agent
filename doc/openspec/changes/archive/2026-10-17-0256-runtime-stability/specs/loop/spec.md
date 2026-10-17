## ADDED Requirements

### Requirement: 流式中断留痕

`astream` SHALL 在**未正常收尾**时留下可落盘的遥测证据：消费方提前关闭（`GeneratorExit`）、
调用被取消（`CancelledError`）或执行体抛出未收尾异常时，循环 SHALL 先记录一条
`loop_aborted` 遥测事件（载荷含**有界**的 `reason`，SHALL NOT 含用户文本 / 异常消息 / 密钥），
随后 `end_trace` **封口**，使本轮已记录的事件经导出器落盘，SHALL NOT 静默丢失。

正常收尾路径 SHALL NOT 产出 `loop_aborted`，其事件序、`trace_observer` 回调时机与
`end_trace` 封口时机 SHALL 逐字不变（回调仍能完整回放，封口仍在回调之后）。中断路径
SHALL NOT 追加助手转录、SHALL NOT 写轮末完成记忆、SHALL NOT 改变既有回滚语义。

#### Scenario: 消费方提前关闭留痕
- **GIVEN** 一次流式执行已产出部分事件，消费方在终态前关闭事件流
- **WHEN** 事件流被关闭
- **THEN** 本轮 trace 新增 `loop_aborted` 并经导出器落盘，trace 不再驻留内存

#### Scenario: 执行体异常留痕
- **GIVEN** 已注入 tracer，执行体在正常收尾前抛出异常
- **WHEN** 异常向外传播
- **THEN** 先记录 `loop_aborted` 并封口本轮 trace，再原样抛出该异常

#### Scenario: 正常收尾不产中断事件
- **GIVEN** 一次正常完成的执行
- **WHEN** 本轮收尾
- **THEN** trace 中**不含** `loop_aborted`，既有事件与封口语义不变

### Requirement: 轮内压实进度与上限

轮内压实（阈值触发与预算降级触发）SHALL 有可观测的进度与总时长上限：

- 阈值压实前后 SHALL 各产出一条事件：`loop.compacting`（载荷含 `round`）与
  `loop.compacted`（载荷含 `round`、`elapsed_ms`、`timeout`）；载荷 SHALL NOT 含正文或摘要。
- 压实总时长 SHALL 有上限（缺省 `120` 秒，可经构造注入覆盖；`None` ⇒ 不设上限）。
  超过上限时 SHALL 记 `maintenance_failed`（`step="compaction_timeout"`）并**放行本轮**：
  本轮继续推进、至多再压实一次，SHALL NOT 因压实超时中断或挂起。
- 未注入压实器时 SHALL NOT 产出上述两条事件（事件面与既有缺省一致）。

#### Scenario: 压实前后产出进度事件
- **GIVEN** 注入压实器且本轮达到压实阈值
- **WHEN** 轮内压实执行
- **THEN** 依次产出 `loop.compacting` 与 `loop.compacted`，后者含非负 `elapsed_ms` 且
  `timeout=False`，其后本轮正常收尾

#### Scenario: 压实超时放行本轮
- **GIVEN** 压实执行超过注入的总时长上限
- **WHEN** 等待超时
- **THEN** 产出 `loop.compacted`（`timeout=True`）并记录
  `maintenance_failed.step="compaction_timeout"`，本轮继续推进至正常终态
