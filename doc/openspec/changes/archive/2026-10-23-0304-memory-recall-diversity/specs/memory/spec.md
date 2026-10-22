# Spec Delta — memory（0304 召回多样性与注入统计）

## ADDED Requirements

### Requirement: 召回的多样性控制与注入统计

`MemoryStore.recall()` SHALL 返回 `RecallResult`（条目 + `matched_count` / `injected_count` /
`excluded_by_budget` / `excluded_by_diversity` / `minimum_budget`）；`read()` SHALL 保持既有签名
与返回类型，语义等价于 `recall(...).entries`。

检索管线 SHALL 在**排名之后、预算之前**施加两道多样性过滤（被滤条目不吃预算、不被复用强化，
且不改变排名顺序）：

- **近重复抑制**：`content_hash` 相同的条目只保留排名最高的一条；旧行哈希为空时按同口径现算。
  正文 `strip()` 为空者 SHALL NOT 参与近重复抑制。
- **同会话上限**：`session_id` 非空的条目，每个会话最多 3 条；`session_id == ""` 的全局条目
  不受该上限约束。调用方已用 `session_id` 参数收窄到单会话时 SHALL NOT 施加该上限
  （结果本就来自同一会话，施加上限只会截断该会话自身的事实面）。

统计口径：`matched_count` 为通过既有硬过滤后进入排名的候选数；`injected_count` 为最终返回数；
`excluded_by_budget` 为预算截断跳过数；`excluded_by_diversity` 为多样性过滤剔除数；
SHALL 满足 `matched_count == injected_count + excluded_by_diversity + excluded_by_budget`。
`minimum_budget` 为再注入第一条被预算跳过条目所需的最小预算（无预算剔除 ⇒ 0）。

本要求 SHALL NOT 引入 kind 配额（`MemoryEntry.kind` 无 procedural 类）或 `source` 级上限
（本仓 `source` 为粗粒度管道标签，按它限流会饿死关键事实）。

#### Scenario: 同会话最多三条

- **GIVEN** 同一 `session_id` 的 4 条命中条目与另一会话的 1 条命中条目
- **WHEN** 以缺省参数 `read()` 检索
- **THEN** 该会话最多返回 3 条；另一会话的条目不受影响

#### Scenario: 会话收窄时不施加上限

- **GIVEN** 同一 `session_id` 的 4 条命中条目
- **WHEN** 以该 `session_id` 为参数 `recall()`
- **THEN** 4 条均可返回，`excluded_by_diversity == 0`

#### Scenario: 全局条目不受会话上限

- **GIVEN** 5 条 `session_id == ""` 的关键事实均命中查询
- **WHEN** `read()` 检索
- **THEN** 5 条均可返回（仅受预算约束）

#### Scenario: 近重复只留最高分

- **GIVEN** 两条正文完全相同（或仅首尾空白不同）的条目与一条不同正文的条目
- **WHEN** `recall()` 检索
- **THEN** 同文条目只返回排名最高的一条，`excluded_by_diversity >= 1`

#### Scenario: 注入统计可返回

- **GIVEN** 命中条目数超过给定预算
- **WHEN** 调用 `recall(..., budget=小值)`
- **THEN** `matched_count == injected_count + excluded_by_diversity + excluded_by_budget`，
  `excluded_by_budget > 0`，`minimum_budget > 0`

#### Scenario: read 兼容

- **GIVEN** 任意检索参数
- **WHEN** 分别调用 `read(...)` 与 `recall(...)`
- **THEN** `read()` 返回的对象与 `recall().entries` 逐条相同（同一列表内容）
