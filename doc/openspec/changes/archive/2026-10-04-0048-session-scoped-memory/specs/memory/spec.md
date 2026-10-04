# Memory Specification Delta

## MODIFIED Requirements

### Requirement: 分层记忆模型
系统 SHALL 按 L0（元策略）→L1（索引）→L2（事实）→L3（SOP/技能）→L4（原始会话）分层存储，层间由轻量索引连通；并 SHALL 在 L2 写入时记录条目的**会话归属**（`session_id`，缺省空串表示未归属会话）——压实、固化与遗忘的「按会话」口径（见「记忆压实」「记忆固化」）一律以该字段归组。

#### Scenario: 分层写入
- **GIVEN** 一条经验需要沉淀
- **WHEN** 记忆系统判断其层级
- **THEN** 写入对应层级，并在 L1 建立最小索引条目

#### Scenario: 写入记录会话归属
- **GIVEN** 一轮属于某会话（`session_id` 非空）的执行产生 L2 沉淀
- **WHEN** 条目写入记忆存储
- **THEN** 该条目的 `session_id` 等于产生它的会话标识，可被压实/固化/遗忘按会话归组

#### Scenario: 未归属写入归缺省分组
- **GIVEN** 一次未携带会话标识的 L2 写入
- **WHEN** 条目写入记忆存储
- **THEN** `session_id` 为空串，归入未归属分组（与既有语义兼容，不影响已落账数据）

#### Scenario: 跨层检索
- **GIVEN** 一个查询命中 L1 索引
- **WHEN** 检索器解析索引
- **THEN** 按热度路由到 L2/L3/L4 取详情，而非全库扫描
