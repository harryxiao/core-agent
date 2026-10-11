# 设计 —— change 0218 情景归纳

## §1 根因取证

| # | 事实 | 证据 |
|---|---|---|
| 1 | 情景类**无专属沉淀 prompt**，复用通用会话摘要 prompt | `memory/store.py::_summarize_sessions` 只调 `summarizer`；无「归纳」接缝 |
| 2 | 会话摘要 prompt 的口径是**滚动合并 + 迁移来源** | `summarize.build_prompt` 有「现有摘要：」槽；`_commit_summary` 把原条目迁 L4 |
| 3 | 程序类 / 语义类各有专属 prompt ⇒ 三类不对称 | `skills/sop._PROMPT_HEAD`、`extract.build_extract_prompt` / `build_relation_prompt` |
| 4 | 归纳产物若与摘要同 `kind` 会**自激** | `_episodic_groups` 判据 `kind == "episodic" and layer == "L2"` ⇒ 回流材料 |

## §2 关键取舍

### §2.1 独立接缝，而非改造摘要 prompt（用户裁决）
摘要器与归纳器的**材料、副作用、产物去向**三重不同（见 proposal「Why」）。合并成一条
prompt ⇒ 任何措辞调整同时改两路行为，**无法局部演进**（违 P3）。故新增**独立**接缝
`episodic_extractor`，与 `key_fact_extractor` / `relation_extractor` 并列。

### §2.2 契约返回**文本**，而非结构化对象
归纳产物是给人读 / 供注入的**结论快照**，没有下游机读消费者（关键事实有
`KeyFact`→`keyfact.<slug>` 的实体幂等键，关系有谓词白名单，二者都必须结构化）。
故契约取 `Callable[[list[MemoryEntry]], str]`（同 `Summarizer`），**不**引入新 dataclass ——
YAGNI（CLAUDE.md §2），也避免为不存在的消费者造抽象。

### §2.3 `kind="semantic"` 是**承重**设计，不是标签选择
`_episodic_groups` 是打分 / 摘要 / 关键事实 / 关系 / （本次）归纳的**唯一材料源**。它的入选
判据是 `kind == "episodic" and layer == "L2"`。归纳产物若取 `kind="episodic"`，下一轮压实即
把它当材料回喂摘要器 —— 形成「摘要 → 归纳 → 摘要」自激环，且每轮都放大一次。取
`kind="semantic"` ⇒ **结构性**排除（而非靠标签约定），并顺带获得「语义条目」的正确分类
（归纳是提炼事实，不是事件）。`tags` 里仍留 `episodic` 作**人读标签**（不承担任何机制）。

### §2.4 每会话一条、覆盖式
归纳的语义是「这段会话到目前做成了什么」——同一会话的旧结论被新结论**取代**，不是累积。
`id=episodic.<key>` 走 `write()` 的既有幂等语义（同 id 覆写）⇒ 条目不增长（P5 token 有界）。
不建多版本索引：**没有**消费者需要历史版本，且压实产物已可由 `trace_id` 回滚。

### §2.5 脱敏在 store 侧无条件执行
承 `_extract_key_facts` 同一红线：**注入的抽取器不构成信任边界**。归纳器由组合根注入，
其输出可能夹带模型**复述**的明文密钥（材料里的取值可能是密钥形态）。故落库前
`redact_secrets` ＋ 截断，方向恒 over-redact。

### §2.6 `session_id=""`（全局层）
归纳结论跨会话可见（同关键事实 / 关系）——「上次这个任务怎么收的」不该被会话边界锁住；
产生它的会话经 `tags` 的 `session:<key>` 溯源。`id` 用 `key`（含会话）⇒ 会话间**不互相覆盖**。

### §2.7 挂点选 `_summarize_sessions` 的会话循环内
与摘要 / 关键事实 / 关系**同材料、同门控（价值门控跳过即一并跳过）、同 trace** ——
一处挂点四处共享，且回滚该轮压实即整批撤销（P2）。**不**新开压实阶段：那会让归纳在
价值门控之外单独跑，与本仓「低价值会话不产衍生物」的既有口径矛盾。

## §3 影响面 / 可逆性 / 红线

- **缺省关**（`episodic_extractor=None`）⇒ `compact()` 守卫不变路径、`_summarize_sessions`
  循环体多一次早返回 ⇒ **压实行为逐字不变**。
- 可逆：条目 `trace_id=compaction.<key>` ⇒ 随该轮压实回滚。
- 红线：脱敏在 store 侧无条件；留痕只报**会话键**，绝不回显摘要 / 事件正文；memo 中不缓存
  明文（缓存键是内容哈希）。
- 宠物 / 子 / 神兽 loop **不接**本能力（归纳是 memory 侧沉淀，不经 loop 注入面）。

## §4 已登记局限

1. 新 `source="episodic"` **未**登记 `_GATE_EXEMPT_SOURCES` / `_FORGETTABLE_SEMANTIC_SOURCES`
   ⇒ 与 `importance_gate` 同开时该条目会**过闸**（可能被拒收 / 降层），且**恒豁免遗忘**
   （长期驻留）。登记为后续候选；本轮保最小爆炸半径。
2. 归纳文本**自由不可机读**（无结构消费面），检索只能靠词法 / 语义相似。
3. 每会话仅一条 ⇒ 超长会话的**早期结论会被后续覆盖稀释**（结论快照语义的固有代价）。
