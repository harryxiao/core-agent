# Memory Specification

## Purpose
记忆系统实现"记忆即光谱"——从 L0 元策略到 L4 归档层的多层级记忆，热/温/冷三档检索温度，承载"无行动不记忆"的沉淀原则。

## Requirements

### Requirement: 分层记忆模型
系统 SHALL 按 L0（元策略）→L1（索引）→L2（事实）→L3（SOP/技能）→L4（归档层：遗忘与压实的下沉目标，检索降权、不参与固化）分层存储，层间由轻量索引连通；并 SHALL 在 L2 写入时记录条目的**会话归属**（`session_id`，缺省空串表示未归属会话）——压实、固化与遗忘的「按会话」口径（见「记忆压实」「记忆固化」）一律以该字段归组。

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

### Requirement: 温度分层检索
系统 SHALL 提供**热/冷两档**检索，热数据常驻内存，冷数据按需加载；检索结果 SHALL 按
**多因子得分**排序——语义相似 × 层结构权重（加性）再经 新鲜度衰减、复用频次
（`1 + log1p(reuse_count)`）、主观重要度（`1 + importance`）**乘性调制**；条目 SHALL 携带
`kind`（episodic / semantic）与 `importance` 元数据，供下沉固化聚合。语义相似 SHALL 经
**可注入 embedder**（缺省词法、可远端向量化）计算，并对检索 query 与未变条目向量做**缓存**
（每次检索 query 至多向量化一次）。

#### Scenario: 热数据即时返回
- **GIVEN** 一个高频使用的 SOP
- **WHEN** 检索该 SOP
- **THEN** 从热区即时返回，无磁盘 IO

#### Scenario: 冷数据按需加载
- **GIVEN** 一个仅存在于 L4 的历史会话
- **WHEN** 检索命中冷数据
- **THEN** 异步加载并按预算注入上下文

#### Scenario: 检索失败降级
- **GIVEN** 检索主路径（热区/索引）发生异常或返回空结果
- **WHEN** 检索失败或未命中
- **THEN** 降级到全库扫描或返回明确未命中结果，不阻断 Agent 主流程，并记录失败原因

#### Scenario: 多因子排序
- **GIVEN** 两条候选记忆与查询的语义相似度相同
- **WHEN** 检索器排序候选
- **THEN** `importance` 更高或 `reuse_count` 更多的条目排在更前；命中条目的 `reuse_count` 递增

#### Scenario: 语义相似经 embedder
- **GIVEN** 注入了 embedder
- **WHEN** 检索一个语义相近但词面不重叠的查询
- **THEN** 以向量相似度参与排序，且本次检索对 query 只向量化一次、未变条目复用缓存向量

#### Scenario: embedder 不可用降级词法
- **GIVEN** 未注入 embedder，或 embedder 调用抛错
- **WHEN** 检索器计算相似度
- **THEN** 降级为词法相似，检索不中断

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

### Requirement: 无行动不记忆
系统 SHALL 只沉淀"行动与结果"产生的经验，不记录未经验证的空想。

#### Scenario: 无行动不写入
- **GIVEN** 模型产出一条未经执行验证的主张
- **WHEN** 尝试写入长期记忆
- **THEN** 被拒绝，需先有行动结果作为证据

### Requirement: 记忆压实
系统 SHALL 定期压实记忆，合并重复条目、归档过期会话、保持 L1 索引最小；并 SHALL 在注入摘要器
（`summarizer`）时，按会话（`session_id`）聚合 episodic 条目、提炼为**一条** `kind="semantic"`
摘要条目（其 `tags` 携带原始条目 id 以追溯原文，`source` 为短标签 `compaction`，`trace_id` 为
`compaction.<session_id>`），并将被聚合的原始条目迁至 L4 归档层（不删除）。未注入摘要器时
SHALL 不做摘要提炼：不写摘要条目、不改动原始条目层级。压实产生的写入与层级迁移 SHALL 全部
可撤销（记入效应追踪，按 `trace_id` 回滚即逆转）。

压实的**聚合范围** SHALL 可**按会话收窄**：`compact` SHALL 接受可选 `session_id` —— **非空**时
SHALL 只聚合**该会话**的 L2 episodic 条目（含其重要度打分写回），SHALL NOT 跨会话提炼或迁移
他会话条目；**空串**时 SHALL 保持**全量**语义（逐字与既有行为一致，供循环内节拍压实使用）。

摘要 SHALL 为**滚动合并**而非覆盖重写：当该会话已存在摘要条目时，系统 SHALL 把**既有摘要内容**
与本次新增 episodic 条目**一并**投喂摘要器，产出**融合既有结论与新增事实**的摘要；系统 SHALL NOT
丢弃既有摘要中未被新摘要显式合并的内容。摘要条目的 `id` 与「每会话至多一条、不增长」口径 SHALL
保持不变（滚动的是**内容**，不是条目数）。

`MemoryStore` SHALL 提供**只读**访问器 `summary_for(session_id) -> MemoryEntry | None`：按 `session_id`
取回该会话既有摘要条目（`id == f"compaction.summary.{session_id or 'default'}"`，口径与摘要写入**同一**）；
无则返回 `None`。该访问器 SHALL NOT 产生任何写入或效应记录，SHALL NOT 变更条目的
`reuse_count` / `importance` / `updated_at`。

滚动合并 SHALL 有一**上界** `MAX_SUMMARY_CHARS`：该上界是既有摘要**投喂摘要器时的节选上限**，
故摘要一旦越过它，下一轮滚动合并即**丢弃**上界之外的既有内容（不可逆稀释）。为把该边界**可见地**
交付上层，`MemoryStore` SHALL 支持注入**提升钩子** `summary_promoter`（契约
`(session_id, MemoryEntry) -> object`，返回值丢弃；缺省 UNWIRED）—— 当某会话摘要**首次越过**该上界
（**既有摘要长度不超过上界**「或该会话尚无既有摘要」而**本次产出摘要长度超过上界**）时，系统 SHALL
把**本次产出的摘要条目**交付钩子**一次**；**已越过**上界的会话 SHALL NOT 重复交付（避免以**已稀释**的
后继摘要覆写上一层已保存的完整内容）。会话标识为空串 SHALL NOT 交付。钩子 UNWIRED（缺省）⇒
SHALL NOT 交付，压实行为**逐字不变**。钩子抛错 SHALL **降级**（不牵连压实本身的写回与迁移，且经
`warnings.warn` 留痕，不静默吞异常）。

#### Scenario: 索引最小化
- **GIVEN** L1 索引膨胀
- **WHEN** 记忆清理 SOP 运行
- **THEN** 合并重复条目，索引回归最小集合

#### Scenario: 摘要提炼并归档
- **GIVEN** 同一会话下有多条 episodic 条目，且记忆存储注入了摘要器
- **WHEN** 压实运行
- **THEN** 产出 `kind="semantic"` 的摘要条目（`tags` 携带原始条目 id），原始条目迁至 L4
  归档层且不被删除（层级由 L2 变为 L4，检索优先级随之降低，仍可审计追溯）

#### Scenario: 滚动合并既有摘要（不丢失）
- **GIVEN** 同一会话已存在一条 semantic 摘要条目，其后又新增若干 episodic 条目
- **WHEN** 再次压实该会话
- **THEN** 投喂摘要器的材料 SHALL **同时**含既有摘要内容与新增条目；产出的摘要条目 SHALL 保留
  既有摘要中的结论（既有内容不被静默丢弃），且仍为**该会话唯一**的摘要条目（id 不变、条目不增长）

#### Scenario: 压实按会话收窄，不触他会话
- **GIVEN** 会话 A 与会话 B 各有若干 L2 episodic 条目，且记忆存储注入了摘要器
- **WHEN** 以 `session_id="A"` 触发压实
- **THEN** 只产出 A 的摘要条目、只迁移 A 的原始条目（B 的条目**逐字不变**、层级与重要度都不动）

#### Scenario: 按会话读取既有摘要（只读）
- **GIVEN** 某会话已完成摘要压实
- **WHEN** `summary_for(<该会话>)`
- **THEN** 返回该会话的摘要条目；`summary_for(<他会话>)` ⇒ `None`；且调用前后
  `audit()` 快照与效应追踪面**逐字不变**（只读，无写入、无效应、不动 `reuse_count` / `importance` / `updated_at`）

#### Scenario: 摘要首次越过上界交付提升钩子一次
- **GIVEN** 某会话既有摘要长度不超过 `MAX_SUMMARY_CHARS`（或该会话尚无既有摘要），
  且 `MemoryStore` 已注入提升钩子
- **WHEN** 本次压实产出的摘要长度超过 `MAX_SUMMARY_CHARS`
- **THEN** 钩子被调用**恰一次**、收到 `(session_id, 该摘要条目)`；**AND WHEN** 该会话再次压实
  （此时既有摘要已越过上界）**THEN** 钩子**不再**被调用

#### Scenario: 未越界或未注入钩子 ⇒ 不交付
- **GIVEN** 压实产出的摘要长度不超过上界；**或** `MemoryStore` 未注入提升钩子
- **WHEN** 压实运行
- **THEN** 无任何钩子调用，摘要写回与条目迁移与变更前**逐字一致**

#### Scenario: 提升钩子抛错降级不牵连压实
- **GIVEN** 注入的提升钩子在调用时抛错
- **WHEN** 「摘要首次越过上界」的压实运行
- **THEN** 摘要条目**仍**写回、原条目**仍**迁 L4（压实不中断），且经 `warnings.warn` 留痕

#### Scenario: 未注入摘要器时降级
- **GIVEN** 记忆存储未注入摘要器
- **WHEN** 压实运行
- **THEN** 不产出摘要条目，原始条目层级保持不变（仅返回评分决策）

#### Scenario: 压实可撤销
- **GIVEN** 已按会话执行摘要压实
- **WHEN** 按该次压实的 `trace_id` 回滚效应
- **THEN** 被聚合的原始条目迁回原层，摘要条目被移除

#### Scenario: 压实失败降级
- **GIVEN** 记忆压实过程中发生写入失败或中途异常
- **WHEN** 压实流程出错
- **THEN** 记忆层不吞异常（向上传播，不写半成品），触发点捕获并经观测通道记录失败原因，
  该会话原始条目保持不变、下次压实可重试，不丢失既有记忆

#### Scenario: 并发压实一致性
- **GIVEN** 记忆压实与写入/检索并发发生
- **WHEN** 压实流程运行时存在并发读写
- **THEN** 通过加锁/事务保证压实不产生数据竞争，并发读写等待或走一致性快照，不丢失条目

`MemoryStore` SHALL 另提供**中期摘要**的产出与读取（会话滑窗「中带」的物化）：
`summarize_slice(session_id, entries, *, max_chars) -> str | None` SHALL 把一段**会话原文**
（`entries` 为上层从转录切出的**临时桩**，**不在库中**；本方法**只读它们、SHALL NOT 将其落库**）
经**既有摘要器**滚合并为**一条** `kind="semantic"` 条目，其 `id` 与 `trace_id` SHALL 分别为
`compaction.mid.<key>` 与 `compaction.mid.<key>`（`key = session_id or "default"`），`source` 为
`compaction`。该产出 SHALL 遵守：

- **滚动合并**：该会话已存在中期摘要时 SHALL 把**既有中期摘要内容**作为材料**首条**一并投喂摘要器；
- **有界 + 脱敏**：写库前 SHALL 无条件执行**密钥形态脱敏**（与关键事实抽取**同源**、方向 over-redact），
  并 SHALL 截断至 `max_chars`（越界即丢弃尾部，不再累积增长）；
- **不迁移来源**：SHALL NOT 迁移任何来源条目的层级（与压实迁移原条目相异 —— 来源为转录桩、本就不在库）；
- **可撤销**：该写入 SHALL 记可撤销效应，按 `trace_id` 回滚即移除该中期摘要条目；
- **降级**：摘要器 UNWIRED、`entries` 为空、或 `max_chars` 非正 ⇒ SHALL 返回 `None` 且**零写入零效应**。

`MemoryStore` SHALL 另提供**只读**访问器 `mid_summary_for(session_id) -> MemoryEntry | None`：按
`session_id` 取回该会话既有中期摘要（`id == f"compaction.mid.{session_id or 'default'}"`），无则
`None`；SHALL NOT 产生任何写入或效应记录，SHALL NOT 变更条目的
`reuse_count` / `importance` / `updated_at`。

#### Scenario: 中期摘要滚动合并既有内容

- **GIVEN** 某会话已存在一条中期摘要条目，其后又切出新增的中带原文桩
- **WHEN** `summarize_slice` 被调用
- **THEN** 投喂摘要器的材料**首条**为既有中期摘要、其后为新增桩；产出仍为**该会话唯一**的中期摘要
  （id 不变、条目不增长）

#### Scenario: 未注入摘要器时中期摘要零写入

- **GIVEN** 记忆存储未注入摘要器（或桩为空 / `max_chars` 非正）
- **WHEN** `summarize_slice` 被调用
- **THEN** 返回 `None`，不写任何条目、不记任何效应

#### Scenario: 中期摘要有界且脱敏且不迁移来源

- **GIVEN** 摘要器产出的文本含**明文密钥形态**字符串且超长，且材料中含已在库的来源条目
- **WHEN** `summarize_slice` 被调用
- **THEN** 落库内容**不含**该明文（脱敏为 `<redacted>`）且长度不超过 `max_chars`；来源条目的层级
  **逐字不变**（不被迁移）

#### Scenario: 中期摘要可撤销

- **GIVEN** 已产出某会话的中期摘要
- **WHEN** 按 `trace_id=f"compaction.mid.<key>"` 回滚效应
- **THEN** 该中期摘要条目被移除

#### Scenario: 按会话读取既有中期摘要（只读）

- **GIVEN** 某会话已产出中期摘要
- **WHEN** `mid_summary_for(<该会话>)`
- **THEN** 返回该中期摘要条目；`mid_summary_for(<他会话>)` ⇒ `None`；且调用前后 `audit()` 快照与
  效应追踪面**逐字不变**

压实（含摘要提炼与关键事实抽取）的**材料** SHALL **排除**带 `failure` 标签的条目：这类条目
SHALL NOT 被摘要提炼或关键事实抽取吸收，SHALL NOT 被迁至 L4（保留于 L2 供按相关度检索）；其**遗忘**
路径 SHALL **不受**此豁免（遗忘语义**逐字不变**）。

#### Scenario: 失败条目不被压实吸收

- **GIVEN** 同一会话下既有若干普通 L2 episodic 条目，又有一条带 `failure` 标签的 L2 episodic 条目，且注入了摘要器
- **WHEN** 压实运行
- **THEN** 摘要条目的 `tags` **不含**该失败条目的 id；该失败条目**仍在 L2**（未被迁至 L4）；同批普通条目照常迁至 L4

#### Scenario: 失败条目仍可被遗忘

- **GIVEN** 一条带 `failure` 标签的 L2 episodic 条目已衰减至遗忘阈值以下
- **WHEN** 遗忘运行
- **THEN** 该条目照常被迁至 L4（失败标签**不豁免**遗忘）
### Requirement: 记忆固化（consolidation）
系统 SHALL 对会话内 episodic 条目**自动打分**并据此**门控固化**：注入 scorer（judgment `score`
原语，JEV 优先、低置信/不可达回退主 LLM）时，SHALL 将分值写回条目的 `importance`（写入可撤销，
打分失败保留原值而非写零）；且 SHALL 仅在会话分值达阈值的会话上执行语义提炼（产出
`kind="semantic"` 条目、原条目迁 L4 归档，口径同「记忆压实」），低价值会话 SHALL 保留 episodic
原状。未注入 scorer、或本轮未取得任何分值（打分失败 / 超出打分上界）时 SHALL 不设价值门槛
（不因缺少决策能力或决策服务抖动而停止固化）。

#### Scenario: 重要度自动写回
- **GIVEN** 注入了 scorer 且存在 L2 episodic 条目
- **WHEN** 固化运行
- **THEN** 条目 `importance` 被写为分值（[0,1]），且该写入可撤销（回滚即恢复旧值）

#### Scenario: 价值门控生效
- **GIVEN** 注入了 scorer，某会话分值低于阈值、另一会话达阈值
- **WHEN** 固化运行
- **THEN** 达标会话提炼为 semantic 条目并归档原条目；低价值会话保持 episodic 原层不动

#### Scenario: 打分失败不降级为零重要度
- **GIVEN** scorer 调用抛错或回退失败
- **WHEN** 固化尝试打分
- **THEN** 该条目 `importance` 保持原值（不被写为 0），该会话不因缺分值而被门槛拦下，
  固化流程不中断

### Requirement: 写入侧重要度闸门（importance write gate）

系统 SHALL 支持注入 **importance scorer**（`MemoryStore` 构造形参，契约
`Callable[[MemoryEntry], float]`，返回 [0,1]）—— 与 `summarizer` / `embedder` /
`key_fact_extractor` 同一依赖方向：memory SHALL NOT import 任何 LLM / rag 抽象，评分器由
L5 组合根注入；**缺省 UNWIRED**。注入后，写入路径 SHALL 先评分再落库：

- 分值低于 `IMPORTANCE_FLOOR` 的条目 SHALL **拒绝入库**（不写、无效应记录、无条目产生），
  并 SHALL 经 `warnings.warn` 留痕（留痕 SHALL 含条目可识别摘要，SHALL NOT 泄露可能含密钥的正文全文）。
- 分值在 `IMPORTANCE_FLOOR` 与 `IMPORTANCE_AMBIT` 之间 ⇒ 条目 SHALL **降层写入 L4 归档层**
  （不拒收但降检索优先级），写入 SHALL 记可撤销效应。
- 分值不低于 `IMPORTANCE_AMBIT` ⇒ 条目按原意向层正常入库，且其 `importance` SHALL 被写为分值
  （写回 SHALL 记可撤销效应，与固化写回同口径）。
- 评分器抛错或返回界外值 ⇒ SHALL **降级放行**（不评分、不拒收、不降层，按原意向层写入），
  `warnings.warn` 留痕，SHALL NOT 牵连写入主流程。
- **未注入（缺省）⇒ 写入行为 SHALL 与现状逐字一致**：不评分、不拒收、不降层、不写 `importance`。

#### Scenario: 未注入评分器时写入不变
- **GIVEN** 未注入 importance scorer 的 `MemoryStore`
- **WHEN** 写入一条条目
- **THEN** 落库层与内容与既有行为逐字一致，无评分留痕、无额外效应

#### Scenario: 低分条目拒收
- **GIVEN** 注入了 scorer，其对该条目返回 0.1（低于 `IMPORTANCE_FLOOR`）
- **WHEN** 写入该条目
- **THEN** 条目不落库（`audit()` 无变化）、无效应记录，且 `warnings.warn` 留痕

#### Scenario: 中间分降层写入
- **GIVEN** 注入了 scorer，其返回 0.3（`IMPORTANCE_FLOOR` ≤ 分 < `IMPORTANCE_AMBIT`）
- **WHEN** 写入该条目
- **THEN** 条目落至 L4 归档层，且该写入可撤销（回滚即按原意向层恢复）

#### Scenario: 高分正常入库并写回分值
- **GIVEN** 注入了 scorer，其返回 0.8
- **WHEN** 写入该条目
- **THEN** 条目按原意向层入库，`importance` 被写为 0.8，且该写回可撤销

#### Scenario: 评分器抛错降级放行
- **GIVEN** 注入的 scorer 调用时抛错
- **WHEN** 写入一条条目
- **THEN** 条目按原意向层正常入库，`warnings.warn` 留痕，写入主流程不中断


### Requirement: 记忆遗忘（forgetting）

系统 SHALL 按衰减评分（新鲜度 × 复用频次 × 重要度）识别低价值记忆并**归档**：评分低于阈值的
**L2 episodic** 条目 SHALL 迁移到 L4 归档层（**不物理删除**、`audit` 可见、检索降权），且每条
迁移 SHALL 记录可逆效应（按 trace 回滚即迁回原层）。**新鲜度衰减 SHALL 被复用信号延缓**：
条目的 freshness 衰减 SHALL 以 `freshness ** (1 / (1 + log1p(reuse_count)))` 调制——`reuse_count`
为 0 时该调制 SHALL 退化为现状（零回归锚点），复用越多衰减越缓（检索命中反哺遗忘曲线）。semantic
条目、L0 元策略与 L3 技能 SHALL 不受遗忘影响；时间戳未知（`ts<=0`）的条目 SHALL 不被惩罚。遗忘
SHALL NOT 中断 Agent 主流程。遗忘 SHALL 由**维护节拍**驱动——循环收尾按维护间隔触发，或由显式
维护入口一次性触发——而非仅依赖压实旁路；节拍只决定"何时跑"，不改上述判据、归档去向与可撤销性。

#### Scenario: 低分条目归档
- **GIVEN** 一条陈旧且从未复用的 L2 episodic 条目
- **WHEN** 遗忘运行
- **THEN** 该条目迁至 L4 归档层，`audit` 仍可见，且返回其撤销句柄

#### Scenario: 复用延缓新鲜度衰减
- **GIVEN** 两条时间戳与 `importance` 相同的 L2 episodic 条目，其一 `reuse_count=3`、另一
  `reuse_count=0`，二者评分均接近遗忘阈值
- **WHEN** 遗忘运行
- **THEN** `reuse_count=0` 的条目被归档，`reuse_count=3` 的条目因衰减被延缓而评分高于阈值、
  层级保持不变

#### Scenario: 未复用条目衰减不变
- **GIVEN** 一条 `reuse_count=0` 的 L2 episodic 条目
- **WHEN** 遗忘运行
- **THEN** 其遗忘评分与引入复用调制前**逐字一致**（调制退化为恒等）

#### Scenario: 节拍驱动遗忘
- **GIVEN** 距上次记忆维护已达维护间隔（或经显式维护入口触发）
- **WHEN** 维护节拍运行
- **THEN** 执行一次遗忘：低价值 L2 episodic 归档、其余不受影响，且不中断 Agent 主流程

#### Scenario: 高价值条目不受影响
- **GIVEN** 一条 `importance` 高或 `reuse_count` 高的 L2 条目
- **WHEN** 遗忘运行
- **THEN** 其评分高于阈值，层级保持不变

#### Scenario: 提炼产物与元策略不被遗忘
- **GIVEN** L2 存在 `kind="semantic"` 条目，L0 存在人格条目，L3 存在技能条目
- **WHEN** 遗忘运行
- **THEN** 三者层级均不变（遗忘只作用于 L2 episodic）

#### Scenario: 遗忘可撤销
- **GIVEN** 某条目已被遗忘归档
- **WHEN** 按该条目的遗忘 trace 回滚效应
- **THEN** 条目迁回 L2 原层

### Requirement: Core Profile 人格注入
系统 SHALL 将 Core Profile 的「人格」分区作为 L0 元策略写入记忆，承载 Agent 的行为特色预设。

#### Scenario: 人格分区写入 L0
- **GIVEN** 全局 Core.md 含「人格」分区
- **WHEN** Agent 启动读取 Core Profile
- **THEN** 该分区内容作为 L0 元策略写入记忆，塑造 Agent 行为特色

### Requirement: 对话转录持久化（非记忆层级）

系统 SHALL 以**按轮追加**（append-only）的方式持久化对话转录：每一条 SHALL 携带 `session_id`、
`role`（`user` / `assistant`）、`content` 与时间戳，落于 `$CORE_STATE_DIR` 下的**单一文件**。
系统 SHALL 支持按 `session_id` 读取该会话转录与取「最近 N 轮」。

转录 SHALL **不是**记忆层级的任何一层（含 L4 —— L4 是遗忘与压实的**归档层**，非对话原文）：
转录条目 SHALL NOT 被 `MemoryStore.read` 返回，SHALL NOT 参与温度分层检索、排名、`reuse_count`
强化、压实、固化与遗忘。转录只能经**按会话的转录读取面**取出。

转录 SHALL 为**单店 + `session_id` 列**（与记忆同店形态一致，不得为每会话建独立存储实例）。

#### Scenario: 追加后可读

- **GIVEN** 某会话一次性追加了若干轮对话
- **WHEN** 另一进程或另一实例按该 `session_id` 读取转录
- **THEN** 读回全部已追加条目，顺序与追加次序一致

#### Scenario: 按会话读取只见本会话

- **GIVEN** 转录中已有 A、B 两个会话的条目
- **WHEN** 以会话 A 的标识读取转录
- **THEN** 返回结果只含 A 的条目

#### Scenario: 反例守门 —— 他人会话转录不可见

- **GIVEN** 转录中已有 A、B 两个会话的条目
- **WHEN** 以会话 B 的标识读取转录
- **THEN** 返回结果**不含** A 的任何条目

#### Scenario: 反例守门 —— 转录不进记忆检索

- **GIVEN** 转录中已有某会话的对话条目
- **WHEN** 经 `MemoryStore.read` 以同一会话标识检索
- **THEN** 检索结果**不含**任何转录条目（转录非记忆层级）

#### Scenario: 文件缺失或坏行降级

- **GIVEN** 转录文件不存在，或其中某一行损坏（非法 JSON）
- **WHEN** 读取转录
- **THEN** 缺失按空转录处理、坏行被跳过，读取不抛错、不阻断主流程

系统 SHALL 支持**三层滑窗的切分读取**：一次读取 SHALL 同时给出**短带原文**与**中带原文** ——
短带为最近 `short_turns` 轮（沿用既有「按 token 从新到旧截断 + 丢弃开头孤儿 assistant 行」语义），
中带为紧邻短带之前的 `mid_turns` 轮（**不**按 token 截断，其内容由中层摘要承接）。两带 SHALL
**不重叠**；轮数不足时短带吃满、中带为空；`short_turns` 非正 ⇒ 两带皆空。该切分 SHALL 只做一次
转录读取（不重复全量解析）。

#### Scenario: 切分短带与中带且不重叠

- **GIVEN** 某会话已有若干轮转录
- **WHEN** 以短层轮数与中层轮数切分读取
- **THEN** 短带 = 末 `short_turns` 轮原文、中带 = 其前 `mid_turns` 轮原文，两带**无交集**

#### Scenario: 短带沿用 token 截断与孤儿行丢弃

- **GIVEN** 短带原文的 token 超过短层 token 上界
- **WHEN** 切分读取
- **THEN** 短带按 token 从新到旧截断、丢弃开头的孤儿 assistant 行；中带**不**截断

#### Scenario: 轮数不足时中带为空

- **GIVEN** 会话轮数少于短层与中层轮数之和
- **WHEN** 切分读取
- **THEN** 短带取尽可用轮次，中带为空（无更旧内容可摘）

#### Scenario: 关闭短层时两带皆空

- **GIVEN** 短层轮数非正
- **WHEN** 切分读取
- **THEN** 短带与中带皆为空
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

### Requirement: 结构化实体抽取（关键事实）

系统 SHALL 提供**结构化关键事实抽取**：在记忆压实时，从**被聚合的 episodic 条目**中抽取
「实体 → 取值」事实，落为 `kind="semantic"` 的记忆条目。抽取器 SHALL 经**依赖注入**交付
（`MemoryStore` 构造形参 `key_fact_extractor`，契约
`KeyFactExtractor = Callable[[list[MemoryEntry]], list[KeyFact]]`；缺省 UNWIRED）—— 与
`summarizer` / `embedder` 同一依赖方向：memory SHALL NOT import 任何 LLM / rag 抽象，模型调用由
L5 组合根注入。抽取材料 SHALL 是**本次压实聚合的 episodic 条目**（即「行动与结果」产生的事件），
承「无行动不记忆」。
承载本轮**行动与结果**序列的那条 L2 条目，其**内容口径**（有界、写入前脱敏）由 `loop`「执行循环」规定 —— 本能力只消费该材料，不另行定义其形态。

落库形态 SHALL 为：`id = f"keyfact.{实体 slug}"`（**同一实体至多一条** —— 重复抽取得**覆盖式
更新**，条目不增长）；`kind="semantic"`；`source="extraction"`（短标签）；`trace_id` 与压实同
（`compaction.<session_id>`）；`tags` SHALL 含 `key_fact` 与 `entity:<slug>`，给出引用时 SHALL 另含
`ref:<ref>`；`content` SHALL 为 `<entity>: <value>`（`value` 已脱敏）；产生它的会话 SHALL 经 `tags` 的
`session:<sid>` 标注溯源（`sid` 非空时）。关键事实 SHALL 属**全局层**（条目 `session_id` SHALL 置
空串、**不**参与会话隔离）—— 实体事实是**跨会话**的长期知识，与 `notes` 「刻意知识不参与会话隔离」
同一取向；**会话归属只作溯源标注，不是隔离维度**。写入 SHALL 走既有唯一写路径
`MemoryStore.write()`（记可撤销效应）⇒ 按 `compaction.<session_id>` 回滚即与压实**一并**逆转。

**密钥红线（本能力的核心约束）**：取值 SHALL **只引用不读取、绝不进记忆**。

- `value` 命中**密钥形态**（已知令牌前缀族 / 长随机串 / `key[:=]value` 赋值式）⇒ SHALL **强制**
  置为字面量 `"<redacted>"`。
- 给出 `ref` 时 ⇒ `value` SHALL **一律**为 `"<redacted>"`（引用式：真实取值在使用时经
  `CoeffectResolver` 注入；**即便**原值不含密钥形态也不得留明文）。**`ref` SHALL 仅当形如
  `coeffect:<名称>` 时才算「给出引用」**；**非该形态**的 `ref`（含模型自造的说明性文字，
  如 `round 1` / `会话事件`）SHALL 视为**无引用** —— 弃用该 `ref`、SHALL NOT 落 `ref:` 标签，
  取值随即按**裸值**判据处理。这是**放宽**而非收紧：模型把「出处说明」当引用回填时，
  不得据此把正常取值抹成 `<redacted>`。
- **fail-closed**：`value` 被判为密钥形态**且无可用 `ref`** ⇒ 该条 SHALL **整条丢弃**（记不住引用
  就**不记**），并 SHALL 经 `warnings.warn` 留痕（留痕 SHALL 含实体名，SHALL NOT 含取值）。
  「无可用 `ref`」SHALL 含 `ref` 为空串**与** `ref` 呈**非** `coeffect:<名称>` 形态两种情形
  —— 自造的说明性引用**不能**为明文密钥背书。
- **抽取器不构成信任边界**：脱敏 SHALL 在**落库前**由 memory 侧**无条件**执行（对抽取器返回的
  每一条都跑）；抽取器抛错或返回**不可解析**的结果 ⇒ SHALL 降级为**不抽取**（`warnings.warn`
  留痕），SHALL NOT 牵连本次压实的摘要写回与条目迁移。「不可解析」SHALL 判为「**有输出但无 JSON
  数组**」（合法但 0 条 SHALL NOT 告警）；该留痕 SHALL NOT 含模型输出正文（可能含明文密钥）。
- 脱敏方向 SHALL 是 **over-redact**（拿不准即多脱敏，落在安全侧），SHALL NOT 出现「拿不准就保留
  明文」。

抽取 SHALL **有界**：单次压实抽取条数 SHALL 有界——上界 SHALL **随本次压实聚合的 episodic 条目数
自适应**：`cap(n) = clamp(ceil(n × KEY_FACTS_RATIO), KEY_FACTS_MIN, KEY_FACTS_MAX)`，且
`KEY_FACTS_MIN` SHALL NOT 低于既有固定上界 `MAX_KEY_FACTS_PER_COMPACT` 的原取值（任何会话长度下
名额 SHALL 不收紧——自适应只放宽）（**同一批**内实体
slug 相同者 SHALL **归并**为一条、**只留首条**落库，归并后条数计额；被归并者 SHALL 经
`warnings.warn` 留痕（留痕含实体名、SHALL NOT 含取值）—— 同批重复是**单次模型响应内的重复枚举**，
区别于跨压实的「重复抽取」，后者由同实体幂等覆盖处理）；`entity` / `value` 长度 SHALL 有界
（`_MAX_FACT_CHARS`），且 SHALL **先脱敏后截断**（截断不得使明文逃逸）；其中 `value` 超长时截断
SHALL **首尾保留**（头尾各半、中以 `…` 连接，总长 SHALL NOT 超过 `_MAX_FACT_CHARS`）。

#### Scenario: 上限随会话长度自适应
- **GIVEN** 两次压实分别聚合 20 条与 200 条 episodic 条目
- **WHEN** keyfact 抽取落库
- **THEN** 两次压实的条数上界按 `cap(n)` 分别计算，长会话的上界不低于短会话，且均落在
  `[KEY_FACTS_MIN, KEY_FACTS_MAX]` 区间

#### Scenario: 自适应上限不低于既有死值
- **GIVEN** 任意聚合条数 n ≥ 0
- **WHEN** 计算 cap(n)
- **THEN** cap(n) ≥ 既有固定上界 `MAX_KEY_FACTS_PER_COMPACT` 的原取值（宽松化而非收紧）

未注入抽取器（缺省）⇒ SHALL NOT 抽取，压实行为（摘要写回、条目迁移、评分）**逐字不变**。

#### Scenario: 未注入抽取器 ⇒ 零抽取、逐字不变
- **GIVEN** `MemoryStore` **未**注入 `key_fact_extractor`（缺省）
- **WHEN** 压实运行
- **THEN** 不产出任何 `key_fact` 条目，摘要写回 / 条目迁移 / 评分与变更前**逐字一致**

#### Scenario: 抽取落库 + 同实体幂等覆盖
- **GIVEN** 注入抽取器，对某会话事件返回两条事实（实体 X、实体 Y）
- **WHEN** 压实该会话
- **THEN** 产出两条 `kind="semantic"` 条目（`source="extraction"`、`tags` 含 `key_fact` 与
  `entity:<slug>`、`trace_id=compaction.<sid>`、`content` 为 `<entity>: <value>`）；条目 `session_id`
  为**空串**（全局层，不参与会话隔离）而 `tags` 含 `session:<sid>`（溯源标注）；**AND WHEN**
  再次压实同一实体且取值已变 **THEN** 仍为**单条**（同 `id` 覆盖式更新，条目不增长）

#### Scenario: 明文密钥强制脱敏
- **GIVEN** 抽取器返回的事实其 `value` 为明文密钥（已知前缀族如 `sk-…`，或长随机串）
- **WHEN** 该事实落库
- **THEN** 落库 `content` **不含**该明文（`value` 为 `"<redacted>"`）——**AND GIVEN** 原值同时给出
  `ref` **THEN** 条目照常落库（`tags` 含 `ref:<ref>`），取值仍为 `"<redacted>"`

#### Scenario: 引用式取值一律脱敏
- **GIVEN** 抽取器返回的事实给出了 `ref`，但其 `value` 是一段**看起来正常**的文本
- **WHEN** 该事实落库
- **THEN** `value` SHALL 为 `"<redacted>"`（有引用即不得留明文），`ref` 进入 `tags`

#### Scenario: fail-closed —— 裸密钥无引用则整条丢弃
- **GIVEN** 抽取器返回的事实其 `value` 是密钥形态**且** `ref` 为空 / 不可用
- **WHEN** 该事实落库
- **THEN** 该条**不落库**（无 `keyfact.*` 条目），且经 `warnings.warn` 留痕（留痕含实体名、
  **不含**取值）；同批**其余**合规事实 SHALL 照常落库

#### Scenario: 抽取器抛错或返回不可解析 ⇒ 降级不抽取
- **GIVEN** 注入的抽取器在调用时抛错，**或**返回不可解析的结果
- **WHEN** 压实运行
- **THEN** 不产出 `key_fact` 条目、经 `warnings.warn` 留痕；摘要条目**仍**写回、原条目**仍**迁 L4
  （压实不中断）

#### Scenario: 关键事实条目随压实一并可撤销
- **GIVEN** 已按会话完成带抽取的压实
- **WHEN** 按 `compaction.<session_id>` 回滚效应
- **THEN** 关键事实条目与摘要条目一并被移除、被聚合的原始条目迁回原层

#### Scenario: 条数与长度有界（先脱敏后截断）
- **GIVEN** 抽取器一次返回超过上界条数的事实，且其中一条取值超长
- **WHEN** 压实运行
- **THEN** 单次落库条数不超过本次 `cap(n)`（`n` 为本次压实聚合的 episodic 条数），
  `entity` / `value` 长度不超过 `_MAX_FACT_CHARS`；**AND** 超长取值在**脱敏之后**才被截断
  （截断产物 SHALL NOT 使明文逃逸）

#### Scenario: 同批同 slug 归并（只留首条 + 留痕）
- **GIVEN** 抽取器**单次**返回两条事实，其实体不同但 slug 相同（如 `API Key` 与 `api-key`），
  **或**两次返回同一实体的**不同取值**
- **WHEN** 压实运行
- **THEN** 落库为**单条** `keyfact.<slug>` 条目，其取值为**首条**的取值；**AND** 被归并者经
  `warnings.warn` 留痕（留痕含实体名、**不含**取值）；**AND** 归并后条数计额（不重复占用本次
  `cap(n)` 名额）

#### Scenario: 解析失败留痕且不含模型输出正文
- **GIVEN** 抽取器返回的文本**非空**但**不含**可解析的 JSON 数组（如「解释文字 + 代码围栏」形态）
- **WHEN** 压实运行
- **THEN** 不产出 `key_fact` 条目，且经 `warnings.warn` 留痕；留痕 SHALL **不含**模型输出正文
  （只报失败事实与文本长度）；**AND GIVEN** 返回的是**合法空数组**（模型明确表示无可抽）
  **THEN** SHALL NOT 告警

#### Scenario: 取值超长 ⇒ 首尾保留（总额度不变）
- **GIVEN** 抽取器返回的事实其 `value` 超过 `_MAX_FACT_CHARS`
- **WHEN** 该事实落库
- **THEN** 落库 `value` 长度 SHALL NOT 超过 `_MAX_FACT_CHARS`，且**同时保留头部与尾部**
  （中以 `…` 连接）—— 而非只留头部

#### Scenario: 非 coeffect 形态的 ref 视为无引用
- **GIVEN** 抽取器返回的事实其 `value` 是一段**看起来正常**的文本，且给出了 `ref` 但**非**
  `coeffect:<名称>` 形态（如 `round 1` / `会话事件`）
- **WHEN** 该事实落库
- **THEN** `ref` 被**弃用**（不落 `ref:` 标签）、取值**按裸值判据**处理 —— **不因该 `ref` 被抹成**
  `<redacted>`（正常文本 SHALL 原样保留）；条目照常落库

#### Scenario: 非 coeffect 形态 ref + 密钥形态取值 ⇒ 整条丢弃
- **GIVEN** 抽取器返回的事实其 `value` 是**密钥形态**，且给出的 `ref` **非** `coeffect:<名称>` 形态
- **WHEN** 该事实落库
- **THEN** 该条 SHALL **不落库**（视同「无可用 `ref`」），并 SHALL 经 `warnings.warn` 留痕
  （含实体名、**不含**取值）；同批**其余**合规事实照常落库
### Requirement: 失效关键事实的运维修复

系统 SHALL 提供**失效关键事实**的运维修复入口：识别**失效条目** —— `tags` 含 `ref:` 标签、该 `ref` **非** `coeffect:<名称>` 形态、且 `content` 取值为 `"<redacted>"`（change `0173` 修复前判据的产物：模型自造的出处说明被当成真引用 ⇒ 取值整条被抹 ⇒ 该条目**已不含任何可用信息**）；对**产生它的会话**（由 `session:<会话标识>` 标签溯源）用该会话的**材料**重抽关键事实 —— 材料为该会话的 episodic 条目（**含已归档 L4 的条目**），重抽 SHALL 复用「结构化实体抽取（关键事实）」的 prompt 与脱敏判据（判据**只有一处定义**，不写第二份）。

修复 SHALL 以**会话**为执行单位，且顺序恒为「**先重抽、成功后才清理**」：

- 重抽**失败**（抽取器抛错）或抽取器**未注入** ⇒ SHALL NOT 删除任何条目（fail-closed：不得以信息丢失换「看起来修好了」）。
- 重抽**成功** ⇒ SHALL 删除该会话产出的**全部旧** keyfact 条目（`tags` 含该会话的 `session:` 标签），随后落重抽结果 —— 重抽产出的实体名与旧条目**不保证重合**（slug 不重合即不覆盖 ⇒ 只删「仍呈失效形态者」会残留死条目，继续参与检索）。
- 删除 SHALL **排除本次重抽已写入的条目 id** —— 同 slug 重抽即覆盖式更新，若一并删除，则刚修好的条目会被自己删掉。

删除前 SHALL 把**待删条目原样**落**一份**备份文件（`$CORE_STATE_DIR/memory.repair.<时间戳>.jsonl`）—— **每次操作恰好一份**（跨会话的待删条目**合并**写入、**共用同一时间戳**；SHALL NOT 每会话各落一份）—— 该文件是本操作**可逆性**的来源（一次性进程内的 `EffectTracker` undo 随进程结束失效），其暴露度与 `memory.jsonl` 同级（同目录、同内容口径 —— 被删条目**本就已脱敏**）。备份**写入失败** ⇒ SHALL NOT 删除**任何**条目（fail-closed；**跨会话一并阻断**，无部分删除）。

修复 SHALL **幂等**：无失效条目时可运行且**不产生任何写入**（含不落备份）。SHALL 提供**只读预演**：报告将识别的失效条目、涉及会话与将清理的条数，SHALL NOT 删除、SHALL NOT 落库。

**密钥红线不变**：重抽结果的脱敏 SHALL 仍由 memory 侧**无条件**执行（抽取器**不构成信任边界**）；备份文件 SHALL NOT 引入新的明文面（失效条目的取值恒为 `"<redacted>"` —— 密钥形态的取值当初即被整条丢弃、从未落库）。

#### Scenario: 识别失效条目
- **GIVEN** 库中并存：一条 `ref:` 标签为 `coeffect:<名称>` 的 keyfact、一条无 `ref:` 标签的正常 keyfact、一条 `ref:` 标签非 `coeffect:` 形态且取值为 `"<redacted>"` 的 keyfact
- **WHEN** 执行修复（预演或实做）
- **THEN** **只有**第三条被识别为失效条目；前两条 SHALL NOT 被识别、SHALL NOT 被删除

#### Scenario: 重抽成功后清理该会话旧条目
- **GIVEN** 某会话产出若干失效 keyfact，且该会话的 episodic 材料仍在（**含已归档 L4 的条目**）
- **WHEN** 执行修复且该会话重抽成功
- **THEN** 该会话的**全部旧** keyfact 条目被删除（含重抽**未**再产出的实体名），重抽结果落库为新的 keyfact 条目；材料取自**全层**（L4 归档条目同样参与重抽）

#### Scenario: 同 slug 重抽不误删
- **GIVEN** 某会话的失效条目 `keyfact.<slug>`，且重抽产出的实体名经 slug 归一后与之**相同**
- **WHEN** 执行修复
- **THEN** 该 id 上落**新**取值（覆盖式更新），且该条目 SHALL NOT 出现在被删集合中（刚修好的条目不得被自己删掉）

#### Scenario: 重抽失败不删条目
- **GIVEN** 某会话有失效条目，且抽取器**抛错**（或抽取器**未注入**）
- **WHEN** 执行修复
- **THEN** SHALL NOT 删除任何条目；报告 SHALL 标明未修复的会话/条目（fail-closed）

#### Scenario: 备份文件先落且失败即不删
- **GIVEN** 多个会话各自重抽成功、**都**存在待删条目
- **WHEN** 备份文件写入失败
- **THEN** SHALL NOT 删除**任何**会话的任何条目（fail-closed 跨会话一并阻断，无部分删除）；
  已落的新条目保留，并以告警留痕

#### Scenario: 待删条目跨会话合并为一份备份
- **GIVEN** 两个会话各自重抽成功、**都**存在待删条目
- **WHEN** 执行修复
- **THEN** 备份文件 SHALL **恰好一份**（同一时间戳，内容为两次会话待删条目的**并集** —— 逐行可解析回条目）；
  报告的备份路径 SHALL 指向该文件

#### Scenario: 幂等与只读预演
- **GIVEN** 库中**无**失效条目（或处于预演模式）
- **WHEN** 再次执行修复（或：以预演模式执行）
- **THEN** 无失效条目时：不产生任何写入（不落备份）；预演模式：只报告识别结果与将清理条数，SHALL NOT 删除、SHALL NOT 落库

#### Scenario: 无会话出处的失效条目不删
- **GIVEN** 一条失效条目**不带** `session:` 标签（无法定位产生它的会话与材料）
- **WHEN** 执行修复
- **THEN** 该条目 SHALL NOT 被删除（无材料即无法重抽），报告 SHALL 标明其不可修复