## ADDED Requirements

### Requirement: 执行结果透出本轮 token 记账

`LoopResult` SHALL 新增 `token_used` 字段（整数，缺省 `0`），值 SHALL 等于该轮收尾时的
`LoopContext.token_used`（沿用「错误与预算控制」规定的记账口径）。该字段 SHALL 只作为
**只读输出**供上层（编排层整任务预算）消费：SHALL NOT 改变循环的预算判定、压实阈值、
终止语义或持久化内容（不进转录 / 记忆 / 检查点 `reply`）；未设置该字段的既有构造 SHALL
保持合法（缺省 `0`）。

#### Scenario: 正常收尾透出记账值

- **GIVEN** 一轮循环正常收尾且 `LoopContext.token_used` 为 N
- **WHEN** 生成 `LoopResult`
- **THEN** `LoopResult.token_used` SHALL 为 N

#### Scenario: 缺省构造向后兼容

- **GIVEN** 既有代码以 `LoopResult(reply=..., trace_id=...)` 构造结果
- **WHEN** 读取 `token_used`
- **THEN** 值 SHALL 为 `0`，不抛异常
