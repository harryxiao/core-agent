# Memory Specification Delta

## MODIFIED Requirements

### Requirement: L2 活跃层软上限

`MemoryStore` SHALL 支持可选的 **L2 活跃层软上限**（构造形参 `l2_soft_max_entries`，
缺省 `None` = 不启用，行为逐字不变）。该形参 SHALL 由组合根从 `memory.l2_soft_max_entries`
配置键读取并注入（见 `configuration` 规格「记忆容量配置」）；未配置 ⇒ `None` ⇒ 逐字不变。
启用后，每次写入落库后 SHALL 检查 L2 条目数；超限 SHALL 先走既有 `forget(threshold)` 衰减
归档路径，仍超限 SHALL 按 `ts` 从旧到新将**可遗忘**条目迁移至 L4（复用既有 `migrate` 路径，
记可撤销效应），直至回到上限内或无可遗忘条目。软上限 SHALL NOT 物理删除条目、SHALL NOT
归档摘要类条目 / L0 / L3、SHALL NOT 阻塞写入主流程（执行失败降级留痕）。

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

#### Scenario: 经配置键启用后写入即收口
- **GIVEN** `memory.l2_soft_max_entries` 已配置且组合根已完成注入
- **WHEN** 写入使 L2 活跃条目数超过该值
- **THEN** 该次写入的落库路径即执行收口，L2 活跃条目数回到上限内（不等待维护节拍）
