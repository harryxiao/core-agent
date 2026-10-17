# Delta — change 0230（memory：跨压实合并 + L2 软上限 + 读预算估算器）

## ADDED Requirements

### Requirement: 关键事实的跨压实合并

跨压实批次重复抽取同一实体时，关键事实 SHALL 按实体 slug **覆盖式更新**既有条目
（`id = f"keyfact.{slug}"`），SHALL NOT 新增条目；更新后 `content` SHALL 为新取值、
`trace_id` / `tags` SHALL 随本次压实刷新（会话溯源随本次压实），但条目**首次出现的时间戳**
（`ts`）SHALL 保留，SHALL NOT 被本次写入重置。同批归并语义（同批同 slug 只留首条）SHALL
保持不变。

#### Scenario: 跨压实同实体合并不新增条目
- **GIVEN** 两个压实批次抽取到同一实体、不同取值
- **WHEN** 第二批压实落库
- **THEN** 仍只有一条 `keyfact.<slug>` 条目，`content` 为第二批取值

#### Scenario: 跨压实更新保留首见时间戳
- **GIVEN** 某实体的关键事实已在第一批压实落库
- **WHEN** 第二批压实覆盖更新该实体
- **THEN** 条目 `ts` 仍等于首次落库时间，未被重置为第二批写入时间

### Requirement: L2 活跃层软上限

`MemoryStore` SHALL 支持可选的 **L2 活跃层软上限**（构造形参 `l2_soft_max_entries`，
缺省 `None` = 不启用，行为逐字不变）。启用后，每次写入落库后 SHALL 检查 L2 条目数；超限
SHALL 先走既有 `forget(threshold)` 衰减归档路径，仍超限 SHALL 按 `ts` 从旧到新将**可遗忘**
条目迁移至 L4（复用既有 `migrate` 路径，记可撤销效应），直至回到上限内或无可遗忘条目。
软上限 SHALL NOT 物理删除条目、SHALL NOT 归档摘要类条目 / L0 / L3、SHALL NOT 阻塞写入
主流程（执行失败降级留痕）。

#### Scenario: 软上限超限触发遗忘归档
- **GIVEN** 启用软上限且写入使 L2 条目数超过上限，其中存在低价值陈旧条目
- **WHEN** 写入落库
- **THEN** 既有遗忘路径先归档低分条目，L2 活跃条目数回到上限内

#### Scenario: 软上限按最旧可遗忘条目收口
- **GIVEN** 启用软上限且仅靠遗忘仍超限（条目评分均高于遗忘阈值）
- **WHEN** 写入落库
- **THEN** 按 `ts` 从旧到新迁移可遗忘条目至 L4，直至回到上限内或无可遗忘条目

#### Scenario: 未启用软上限行为不变
- **GIVEN** 未设置 `l2_soft_max_entries`（缺省 `None`）
- **WHEN** 任意写入
- **THEN** 不触发任何上限检查，L2 条目层级与引入本能力前逐字一致

### Requirement: 记忆读预算的可注入估算器

`MemoryStore` 的检索预算裁剪 SHALL 支持可注入的 token 估算器（构造形参 `token_estimator`）；
注入后 SHALL 使用该实现计算条目成本；未注入时 SHALL 回落共享启发式估算器，行为逐字不变。

#### Scenario: 注入估算器替换读预算测量
- **GIVEN** `MemoryStore` 注入了返回固定分值的 `TokenEstimator`
- **WHEN** 检索并按预算裁剪
- **THEN** 条目成本取自注入实现，裁剪结果随之变化

#### Scenario: 未注入估算器读预算不变
- **GIVEN** `MemoryStore` 未注入估算器
- **WHEN** 检索并按预算裁剪
- **THEN** 使用共享启发式估算器，行为与引入本能力前逐字一致
