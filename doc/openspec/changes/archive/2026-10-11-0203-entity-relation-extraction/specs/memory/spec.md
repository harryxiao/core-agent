# Memory Specification Delta — 实体关系抽取（change 0203）

## ADDED Requirements

### Requirement: 实体关系抽取（relations）

系统 SHALL 提供**实体关系抽取**：在记忆压实时，从**被聚合的 episodic 条目**中抽取
「头实体 — 谓词 — 尾实体」三元组，落为 `kind="semantic"` 的记忆条目。关系抽取器 SHALL 经
**依赖注入**交付（`MemoryStore` 构造形参 `relation_extractor`，契约
`RelationExtractor = Callable[[list[MemoryEntry]], list[Relation]]`；缺省 UNWIRED）—— 与
`key_fact_extractor` / `summarizer` / `embedder` 同一依赖方向：memory SHALL NOT import 任何
LLM / rag 抽象。关系抽取 SHALL 与关键事实抽取**分为两个独立接缝**（`relation_extractor`
SHALL NOT 与 `key_fact_extractor` 合并 —— 合并会改关键事实抽取 prompt 的字节）。

**谓词 SHALL 闭合。** 谓词 SHALL 取自**闭合白名单**（中英双语变体），且 SHALL **归一化**为
其**规范英文谓词**后落库（如「依赖」⇒ `depends_on`）。归一化后**不在**白名单内 ⇒ 该三元组
SHALL **整条丢弃**，并 SHALL 经 `warnings.warn` 留痕（留痕 SHALL 含头 / 尾实体名与**原始**谓词，
SHALL NOT 含除实体名与谓词名以外的任何文本）。谓词开放 ⇒ 使关系「图」不可遍历、并新增一个
**无界自由文本字段**（新的密钥携带面）、且令幂等去重的基数失控 ⇒ 故 SHALL 闭合。

落库形态 SHALL 为：`id = f"relation.{slug(head)}--{predicate}--{slug(tail)}"`；
`content = f"{head} --{predicate}--> {tail}"`；`kind="semantic"`；`source="relation"`；
`trace_id` 与压实同（`compaction.<session_id>`）；`session_id` SHALL 置**空串**（全局层 ——
跨会话的长期知识，同关键事实）；`tags` SHALL 含 `relation` 与 `entity:<slug(head)>` /
`entity:<slug(tail)>` / `predicate:<规范谓词>`，产生它的会话非空时 SHALL 另含 `session:<sid>`
（**只作溯源，不是隔离维度**）。**同一三元组** SHALL **幂等覆盖**（同 `id`，条目不增长）。
写入 SHALL 走既有唯一写路径 `MemoryStore.write()`（记可撤销效应）⇒ 按 `compaction.<session_id>`
回滚即与压实**一并**逆转。

**密钥红线（本能力的核心约束）**：关系 SHALL **不携带任何取值**；`head` / `tail` 任一侧、
或**原始**谓词，呈**密钥形态** ⇒ 该三元组 SHALL **整条丢弃**（fail-closed）并留痕。
留痕中的实体名 / 谓词名 SHALL **先经同一脱敏判据**（over-redact）—— head 本身可能就是密钥，
直接回显即泄漏。三元组 SHALL NOT 设 `coeffect:` 引用逃生口（与关键事实的**有意不对称**：
关系没有可引用之物）。

抽取 SHALL 有界：单次压实抽取条数上界 SHALL **复用关键事实的同一把旋钮**（`relation_cap`
SHALL **等于** `key_fact_cap`，SHALL NOT 另起第二组常量）；**同一批内**完整三元组相同者 SHALL
归并为一条、**只留首条**；`head` / `tail` 长度 SHALL 有界（`_MAX_FACT_CHARS`）、`content`
SHALL 有界（`_MAX_MEMORY_ENTRY`），且 SHALL **先脱敏后截断**。

关系条目 SHALL NOT 回喂压实材料（`kind="semantic"` 使其不入选只收 `kind="episodic"` 的材料面）。
关系条目 SHALL **到达**「相关事实」注入面（其 `source="relation"` 不在该面的排除前缀内）。

未注入抽取器（缺省）**或**配置关闭（`memory.relation_extract` 缺省 **`False`**）⇒ SHALL NOT
抽取，压实行为（摘要写回、条目迁移、评分、关键事实）**逐字不变**。

#### Scenario: 未注入抽取器 ⇒ 零关系、逐字不变

- **GIVEN** `MemoryStore` **未**注入 `relation_extractor`（缺省）
- **WHEN** 压实运行
- **THEN** 不产出任何 `relation` 条目；摘要写回 / 条目迁移 / 评分 / 关键事实与变更前**逐字一致**

#### Scenario: 落库形态与幂等覆盖

- **GIVEN** 注入抽取器并返回一个三元组 `(A, depends_on, B)`
- **WHEN** 该三元组在一次压实时落库
- **THEN** 条目 `id = "relation.<slug(A)>--depends_on--<slug(B)>"`、`content = "A --depends_on--> B"`、
  `kind="semantic"`、`source="relation"`、`session_id=""`、`trace_id="compaction.<session_id>"`、
  `tags` 含 `relation` 与 `entity:` / `predicate:` 标注；且**同一三元组两次**抽取后仍只有**一条**条目

#### Scenario: 中文谓词归一化为规范英文

- **GIVEN** 抽取器返回谓词为中文变体（如「依赖」）
- **WHEN** 落库
- **THEN** 条目的 `predicate` 标注与 `id` 均用**规范英文谓词**（`depends_on`）

#### Scenario: 未知谓词丢弃并留痕

- **GIVEN** 抽取器返回一个谓词，其归一化结果**不在**白名单内
- **WHEN** 归一化落库
- **THEN** 该三元组 **SHALL NOT** 落库；并以 `warnings.warn` 留痕，留痕含头 / 尾实体名与**原始**
  谓词、SHALL NOT 含任何取值

#### Scenario: 密钥形状的实体 ⇒ 整条丢弃且留痕不回显明文

- **GIVEN** 抽取器返回的三元组中，`head` 或 `tail` 呈密钥形态
- **WHEN** 脱敏落库
- **THEN** 该三元组 **SHALL NOT** 落库；留痕中的实体名 SHALL **已脱敏**（命中处替换为占位、
  SHALL NOT 出现明文密钥）

#### Scenario: 空实体丢弃

- **GIVEN** 抽取器返回的三元组中，`head` 或 `tail` 去空白后为空串
- **WHEN** 归一化落库
- **THEN** 该三元组 **SHALL NOT** 落库

#### Scenario: 上界与关键事实同一把旋钮

- **GIVEN** 一次压实聚合 n 条 episodic 条目，抽取器返回**超过** `relation_cap(n)` 条的合法三元组
- **WHEN** 落库
- **THEN** 落库条数恰为 `relation_cap(n)`，且 `relation_cap` 与 `key_fact_cap` **同值**（同一把旋钮）

#### Scenario: 关系不入压实材料

- **GIVEN** 已落库若干 `relation` 条目
- **WHEN** 收集压实材料（`kind="episodic"` 且 `layer="L2"`）
- **THEN** `relation` 条目 **SHALL NOT** 入选（其 `kind="semantic"`）

#### Scenario: 关系随压实回滚一并撤销

- **GIVEN** 一次压实同时产生摘要与关系条目（同一 `compaction.<key>` trace）
- **WHEN** 回滚该 trace
- **THEN** 关系条目 **SHALL** 与压实产物**一并**被撤销

#### Scenario: 关系到达「相关事实」注入面

- **GIVEN** 已落库一条 `relation` 条目，且注入面按 `source` 前缀排除压实产物
- **WHEN** 装配本轮事实
- **THEN** 该关系（渲染为 `head --predicate--> tail`）**SHALL** 出现在事实面
