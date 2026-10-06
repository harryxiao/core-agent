# Memory Specification Delta

## ADDED Requirements

### Requirement: 来源前缀排除与放行（读取面）

系统 SHALL 在记忆检索的读取面支持**来源前缀排除**：`source` 前缀命中 `exclude_source_prefixes` 的条目
SHALL 在**排名与预算之前**剔除 —— 被剔除项 SHALL NOT 占用 token 预算、SHALL NOT 被复用计数
（`reuse_count`）强化，与「按会话隔离的检索」的会话过滤**同一口径**且可叠加。

排除面 SHALL 支持**例外面** `allow_source_prefixes`：**同时**命中排除前缀与放行前缀的条目 SHALL 被**放行**
（「排除某类来源，但放行其中的指定前缀」）。两参数缺省均为空元组 ⇒ 检索语义与既往**逐字一致**；
放行面在排除面为空时 SHALL NOT 产生任何效果（无排除即无所放行）。

命名空间封存（如主 Agent 侧的 `source=beast.*`）SHALL 经该排除面表达，SHALL NOT 以物理删除或层间迁移实现。

#### Scenario: 排除面命中即剔除
- **GIVEN** 库中含 `source` 前缀命中排除项的条目与未命中项的条目
- **WHEN** 以该排除前缀检索
- **THEN** 命中项不出现，未命中项照常参与排名与预算

#### Scenario: 放行面是排除面的例外
- **GIVEN** 某命名空间下既有**自身**条目又有他者条目
- **WHEN** 以该命名空间前缀排除、并放行**自身**前缀检索
- **THEN** 自身条目出现，他者条目**不出现**（放行面只放行给定前缀，不解除对余者的排除）

#### Scenario: 无排除时放行面无效果
- **GIVEN** 未给出任何排除前缀
- **WHEN** 给出放行前缀检索
- **THEN** 结果与不给出放行前缀时**逐字一致**（放行面不改动检索语义）

#### Scenario: 缺省调用语义不变
- **GIVEN** 既有调用方不传排除面与放行面
- **WHEN** 检索
- **THEN** 行为与引入该能力之前**逐字一致**（两参数缺省为空元组）
