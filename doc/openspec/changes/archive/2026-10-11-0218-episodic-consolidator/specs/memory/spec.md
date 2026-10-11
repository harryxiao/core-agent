# Memory Specification Delta — 情景归纳（change 0218）

## ADDED Requirements

### Requirement: 情景归纳（episodic consolidation）

系统 SHALL 提供**可注入的情景归纳器**（`MemoryStore` 构造形参 `episodic_extractor`，契约
`EpisodicExtractor = Callable[[list[MemoryEntry]], str]`；缺省 UNWIRED ⇒ 不归纳、行为逐字不变），
在**同一批**被压实的会话 episodic 条目上产出**情景归纳文本**（目标 / 经过 / 结果 / 教训），
落为一条 `kind="semantic"`、`source="episodic"` 的 L2 条目。归纳器 SHALL 经**依赖注入**交付，
与 `key_fact_extractor` / `relation_extractor` / `summarizer` / `embedder` 同一依赖方向
（memory SHALL NOT import 任何 LLM / rag 抽象，prompt 文本属 memory 域、生产侧由 L5 组合根注入
模型调用）。归纳器**不构成信任边界** ⇒ 落库前 SHALL 由 store 侧**无条件**执行 `redact_secrets`
脱敏并截断至有界长度。

- **专属 prompt**：情景归纳 prompt SHALL **独立于**会话摘要 prompt —— 二者材料口径不同
  （摘要器把「既有摘要」当**滚动合并**输入并**迁移**来源条目，归纳器只看本批 episodic 条目
  且**不迁移**任何条目），共用文本会使两路互相污染。归纳 prompt SHALL 明写四段结构
  （目标 / 经过 / 结果 / 教训）与「只输出归纳、不复述过程」。
- **条目形状**：`id=episodic.<key>`（`key = session_id or "default"`）⇒ **每会话至多一条**；
  同一会话再次归纳 SHALL **覆盖式**更新（同 `id` 覆写、条目数不增长）。`tags` SHALL 含
  `episodic` 与 `session:<key>`（会话溯源）；`session_id` SHALL 置空（全局层，同关键事实 /
  关系条目）；`trace_id` SHALL 为 `compaction.<key>` ⇒ 随该轮压实一并可撤销。
- **不参与摘要材料（承重）**：归纳产物 SHALL NOT 被 `_episodic_groups` 选中（其判据为
  `kind == "episodic"` 且 `layer == "L2"`）⇒ SHALL NOT 回喂摘要器 / 关键事实抽取器 ——
  若回喂即形成「摘要 → 归纳 → 摘要」的自激环。该约束 SHALL 由条目 `kind` 承重，而不是靠
  标签或来源串的约定。
- **异常降级**：归纳器抛错 / 返回空（或纯空白）文本 ⇒ **整条不写**、留痕（告警只报**会话键**、
  SHALL NOT 回显摘要或事件正文 —— 承「密钥只引用不读取」红线），SHALL NOT 牵连会话摘要、
  关键事实抽取与压实主流程。

#### Scenario: 注入归纳器时产出情景条目
- **GIVEN** 某会话有 L2 episodic 条目，且 `MemoryStore` 注入了情景归纳器
- **WHEN** 对该会话执行记忆压实
- **THEN** 落一条 `id=episodic.<key>`、`source="episodic"`、`kind="semantic"` 的 L2 条目，内容为归纳文本，`trace_id` 为 `compaction.<key>`

#### Scenario: 未注入归纳器时逐字不变
- **GIVEN** 同一批 L2 episodic 条目，`MemoryStore` 未注入情景归纳器
- **WHEN** 对该会话执行记忆压实
- **THEN** 不出现任何 `source="episodic"` 条目，且会话摘要与关键事实产物与「注入一个恒返回空串的归纳器」时**逐字相同**

#### Scenario: 每会话至多一条、覆盖式更新
- **GIVEN** 某会话已有 `episodic.<key>` 归纳条目
- **WHEN** 该会话再次被归纳（后续压实）
- **THEN** 归纳条目按同一 `id` **覆盖**更新（`id` 不变、该会话仍只此一条），不新增第二条

#### Scenario: 归纳产物不回喂摘要器
- **GIVEN** 某会话已落地一条 `source="episodic"` 的归纳条目，且该会话又有新的 episodic 条目
- **WHEN** 该会话再次被压实
- **THEN** 该归纳条目**不出现**在摘要器材料与关键事实抽取材料中（不予回喂，无自激环）

#### Scenario: 脱敏与有界
- **GIVEN** 情景归纳器返回含密钥形态取值且超长的一段文本
- **WHEN** 归纳条目落库
- **THEN** 落盘内容的密钥形态取值已脱敏（替换为引用占位），且长度不超过有界上限

#### Scenario: 归纳失败降级不牵连压实
- **GIVEN** 情景归纳器在归纳某会话时抛错
- **WHEN** 对该会话执行记忆压实
- **THEN** 不落归纳条目、记录告警（只报会话键、不回显正文），而会话摘要与关键事实抽取**照常完成**
