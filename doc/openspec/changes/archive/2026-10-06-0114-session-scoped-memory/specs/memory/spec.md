# Memory Specification Delta

## ADDED Requirements

### Requirement: 按会话隔离的检索

系统 SHALL 使记忆检索接受可选的**调用方会话标识** `session_id`（缺省空串 = 未归属调用者）。
标识**非空**时，检索结果 SHALL **只含**两类条目：① 归属该会话（`session_id` 等于该标识）的条目；
② **全局层**——未归属条目（`session_id` 为空串）、L0 元策略（人格）、以及**文档化笔记层**。
标识**为空串**时 SHALL NOT 施加会话过滤（检索语义与既往**逐字一致**，未归属调用者不是「某个会话」）。

会话过滤 SHALL 在**排名与预算之前**生效——被滤除的条目 SHALL NOT 占用 token 预算、
SHALL NOT 被复用计数（`reuse_count`）强化，与既有来源前缀排除（`exclude_source_prefixes`）**同一口径**；
两重过滤 SHALL 可叠加。

本 Requirement 只约束**检索面**（喂给推理的事实来源）。`ui` 的 `get_memory(session_id)` **展示面**合同不变
（仍只返回归属该会话的条目）——展示面严于推理面是**有意**的：推理面必须保留全局层，否则人格与笔记进不了 prompt。

#### Scenario: 会话内检索只见本会话与全局层

- **GIVEN** 库中含会话 A 的条目、会话 B 的条目、以及未归属的全局层条目
- **WHEN** 以 A 的会话标识检索
- **THEN** 结果含 A 的条目与全局层条目，**不含** B 的条目

#### Scenario: 会话之间互不可见（反例守门）

- **GIVEN** 会话 A 已沉淀一条事实
- **WHEN** 以会话 B 的标识检索同一 query
- **THEN** 该事实**不出现**在结果中

#### Scenario: 未归属调用者不过滤（兼容）

- **GIVEN** 同上的三类条目
- **WHEN** 以空标识检索
- **THEN** 三类条目都可出现（与既往检索语义逐字一致）

#### Scenario: 过滤先于预算

- **GIVEN** 被会话滤除的条目与预算恰好将满
- **WHEN** 检索
- **THEN** 被滤除项不占预算、`reuse_count` 不递增，同预算下可召回更多本会话条目

#### Scenario: 会话过滤与来源排除可叠加

- **GIVEN** 同时给出会话标识与来源前缀排除项
- **WHEN** 检索
- **THEN** 两类过滤同时生效（命中任一排除条件的条目都不出现）
