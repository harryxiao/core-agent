# Delta — change 0230（loop：预算溢出降级续跑）

## ADDED Requirements

### Requirement: 预算溢出的降级续跑

token 预算触顶 SHALL 先尝试**一次降级**再终止：已注入压实器时，本轮 SHALL 至多触发一次
强制压实（复用轮内 `compacted` 闸门防重入），并为模型**再给一轮**收尾机会；该收尾轮内任务
完成（`ctx.done()`）⇒ SHALL 按正常完成收口，SHALL NOT 以 `TOKEN_BUDGET_EXCEEDED` 覆盖已完成的
回复；收尾轮仍未完成 ⇒ SHALL 以 `TOKEN_BUDGET_EXCEEDED` 终止。降级 SHALL 每轮至多一次
（`budget_retried` 标记），SHALL NOT 无限重试。未注入压实器 ⇒ SHALL 保持既有行为（预算触顶
立即终止，零额外轮次）。降级发生 SHALL 经 trace 留痕（便于诊断预算配置过小），SHALL NOT
改变既有终止码或事件类型。

#### Scenario: 预算触顶先压实再重试一轮
- **GIVEN** 已注入压实器且本轮记账值达到 token 预算
- **WHEN** 一步执行完毕判定预算
- **THEN** 先触发一次强制压实（若本轮尚未压实），记 `budget_retry` 留痕，再允许模型执行一轮

#### Scenario: 收尾轮完成则正常收口
- **GIVEN** 预算触顶并进入收尾轮
- **WHEN** 收尾轮产出终止动作并完成本轮
- **THEN** 按正常完成收口，回复为模型产出，不标记 `TOKEN_BUDGET_EXCEEDED`

#### Scenario: 收尾轮仍未完成则终止
- **GIVEN** 预算触顶并进入收尾轮
- **WHEN** 收尾轮仍未完成且记账值仍不低于预算
- **THEN** 以 `TOKEN_BUDGET_EXCEEDED` 终止（每轮至多一次降级，不重复重试）

#### Scenario: 未注入压实器行为不变
- **GIVEN** 未注入压实器
- **WHEN** 本轮记账值达到 token 预算
- **THEN** 立即以 `TOKEN_BUDGET_EXCEEDED` 终止，SHALL NOT 额外执行轮次
