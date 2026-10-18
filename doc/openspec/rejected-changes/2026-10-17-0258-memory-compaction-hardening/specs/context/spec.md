# context — 压实触发的预算裁决单一口径（change 0258 提案）

## ADDED Requirements

### Requirement: 压实触发的预算裁决单一口径

「何时压实」与「压实到什么程度」的裁决 SHALL 收敛到 `BudgetManager`：
`BudgetManager.should_compact(transcript_chars, turn_count)` SHALL 在预算关闭时退化为既有
步数阈值判定（阈值语义逐字不变），在预算开启时由 `enforce` 的裁决结果驱动。
`DefaultLoop._should_compact` SHALL 删除并改以 `BudgetManager.should_compact` 为唯一调用点；
「必留项」定义 SHALL 只存在于 `budget.py` 一处（`_trim` 与 `should_compact` 共享同一份
keep-list 计算）。`_budget_retry` 降级路径 SHALL 仍由 loop 编排。

#### Scenario: 预算关闭退化为步数阈值
- **GIVEN** token 预算关闭（`token_budget <= 0`）
- **WHEN** 本轮工具步数达到阈值
- **THEN** 压实触发，且阈值边界与改造前逐字一致

#### Scenario: 预算开启由 enforce 驱动
- **GIVEN** token 预算开启且装配结果超预算
- **WHEN** 判定是否压实
- **THEN** 由 `BudgetManager` 的同一份预算裁决给出结果，loop 不再维护独立 token 估算

#### Scenario: 必留项单点定义
- **GIVEN** `_trim` 与 `should_compact` 同时需要必留项集合
- **WHEN** 计算必留项
- **THEN** 两者读取同一份 keep-list 计算，不出现两处口径漂移
