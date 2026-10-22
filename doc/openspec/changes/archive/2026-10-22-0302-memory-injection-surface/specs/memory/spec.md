# memory — 读取面层过滤（change 0302）

## ADDED Requirements

### Requirement: 记忆检索的层过滤（读取面）

系统 SHALL 支持在记忆检索的读取面按**层**过滤：`read(..., layers=(...))` 接受层白名单
（`L0` / `L1` / `L2` / `L3` / `L4` 的任意子集）。白名单**非空**时，检索结果 SHALL **只含**
所列层的条目；层过滤 SHALL 在**排名与预算之前**生效 —— 被滤除条目 SHALL NOT 占用 token
预算、SHALL NOT 被复用计数（`reuse_count`）强化（与 `exclude_source_prefixes`、会话过滤、
`include_forgotten` **同一口径**），并 SHALL 与上述过滤器**叠加**。白名单为**空元组**（缺省）
⇒ 不施加层过滤，检索语义与既往**逐字一致**。

本 Requirement 只约束**读取面**；写入、迁移、压实与审计的层语义不变。

#### Scenario: 层白名单只返回指定层
- **GIVEN** 库中含 L0 / L2 / L4 条目，且内容均与查询相关
- **WHEN** 以 `layers=("L2",)` 检索
- **THEN** 结果只含 L2 条目，L0 与 L4 条目都不出现

#### Scenario: 层过滤先于预算
- **GIVEN** L4 归档条目内容长、排序得分高，且预算恰好只够一条
- **WHEN** 以 `layers=("L2",)` 检索
- **THEN** L2 条目被返回（L4 不占预算），被滤条目 `reuse_count` 不递增

#### Scenario: 缺省不过滤（兼容）
- **GIVEN** 同上的三层条目
- **WHEN** 未传 `layers`（或传空元组）检索
- **THEN** 三层条目都可出现（检索语义与既往逐字一致）

#### Scenario: 与来源排除和会话过滤叠加
- **GIVEN** 同时给出层白名单、来源前缀排除与会话标识
- **WHEN** 检索
- **THEN** 三类过滤同时生效（命中任一排除条件的条目都不出现）
