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

命中条目的复用强化 SHALL **落盘持久化**：`reuse_count` 的递增 SHALL 写入持久后端
（SHALL NOT 只存在于进程内）—— 因该计数经 `1 + log1p(reuse_count)` 与
`freshness ** (1 / (1 + log1p(reuse_count)))` 参与排序与**遗忘曲线**调制，跨会话丢失强化会使
「反复被召回的条目」在重启后退化为从未复用 ⇒ 衰减不再被延缓。写回 SHALL **只**覆盖本次检索
**选中**（进入结果预算）的条目（非选中候选 SHALL NOT 被写、SHALL NOT 被强化 —— 与既有语义
逐字一致）⇒ 写放大有界于选中集。每条写回 SHALL 记录**可撤销效应**（按 trace 回滚即把
`reuse_count` 还原为强化前的值）。

复用强化的**落盘** SHALL 按**单次检索批量提交**：后端支持批量写（`put_many`）时，一次检索的
全部选中条目 SHALL 经**一次批量落盘**写回（SHALL NOT 逐条触发全量重写）；后端未提供批量写时
SHALL 逐条写回（语义不变）。批量写 SHALL 与逐条写回**同一可撤销语义**：每条写回仍各记一条
可撤销效应，按 trace 回滚即把各自 `reuse_count` 还原为强化前的值。

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

#### Scenario: 复用强化跨会话持久
- **GIVEN** 一条命中的记忆条目，其 `reuse_count` 在检索后递增并按预算落盘
- **WHEN** 以**同一持久后端**重新装载记忆（模拟进程重启 / 跨会话）
- **THEN** 该条目的 `reuse_count` 保持强化后的值（SHALL NOT 退回 0）；且该次写回 SHALL 可经
  trace 回滚而还原为强化前的值

#### Scenario: 语义相似经 embedder
- **GIVEN** 注入了 embedder
- **WHEN** 检索一个语义相近但词面不重叠的查询
- **THEN** 以向量相似度参与排序，且本次检索对 query 只向量化一次、未变条目复用缓存向量

#### Scenario: embedder 不可用降级词法
- **GIVEN** 未注入 embedder，或 embedder 调用抛错
- **WHEN** 检索器计算相似度
- **THEN** 降级为词法相似，检索不中断

#### Scenario: 复用强化批量落盘
- **GIVEN** 一次检索选中多条条目，且后端提供批量写入口
- **WHEN** 复用强化写回
- **THEN** 本次检索只触发**一次**批量落盘（不逐条重写），且每条仍各留一条可撤销效应

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
他会话条目；**空串**时 SHALL 保持**全量**语义（逐字与既有行为一致）—— 该全量语义 SHALL **保留给显式调用**（CLI / 运维命令面），**循环内路径**（轮内压实与维护节拍）SHALL **一律以本轮会话标识聚合**（标识为空串时按上句全量语义聚合，与既往一致）。

摘要 SHALL 为**滚动合并**而非覆盖重写：当该会话已存在摘要条目时，系统 SHALL 把**既有摘要内容**
与本次新增 episodic 条目**一并**投喂摘要器，产出**融合既有结论与新增事实**的摘要；系统 SHALL NOT
丢弃既有摘要中未被新摘要显式合并的内容。摘要条目的 `id` 与「每会话至多一条、不增长」口径 SHALL
保持不变（滚动的是**内容**，不是条目数）。

摘要条目落库前 SHALL 由 store 侧**无条件**执行 `redact_secrets`（与中层摘要 / 情景归纳同一红线
口径，方向 over-redact；注入的摘要器**不构成信任边界**）—— 密钥只引用不读取、绝不进记忆。
该脱敏 SHALL NOT 改变未命中密钥形态的正文（逐字不变）。

`MemoryStore` SHALL 提供**只读**访问器 `summary_for(session_id) -> MemoryEntry | None`：按 `session_id`
取回该会话既有摘要条目（`id == f"compaction.summary.{session_id or 'default'}"`，口径与摘要写入**同一**）；
无则返回 `None`。该访问器 SHALL NOT 产生任何写入或效应记录，SHALL NOT 变更条目的
`reuse_count` / `importance` / `updated_at`。

滚动合并 SHALL 有一**上界** `MAX_SUMMARY_CHARS`：该上界是既有摘要**投喂摘要器时的节选上限**。节选 SHALL 为**首尾保留**（而非仅截头）：既有摘要越过上界时，投喂摘要器的既有摘要 SHALL 由**首部**（约 `1200` 字）＋**省略标记**（标明中略字数）＋**尾部**（约 `800` 字）构成，且总节选长度 SHALL **不超过** `MAX_SUMMARY_CHARS` —— 既保上界有界（token 有界），又使**最新结论所在的尾部**不再被无声销毁；未越界时 SHALL **逐字**投喂全文。**越界判据 SHALL 读取既有摘要的全体长度**（不受本节选影响）⇒「首次越过上界」的提升交付语义**逐字不变**。为把该边界**可见地**
交付上层，`MemoryStore` SHALL 支持注入**提升钩子** `summary_promoter`（契约
`(session_id, MemoryEntry) -> object`，返回值丢弃；缺省 UNWIRED）—— 当某会话摘要**首次越过**该上界
（**既有摘要长度不超过上界**「或该会话尚无既有摘要」而**本次产出摘要长度超过上界**）时，系统 SHALL
把**本次产出的摘要条目**交付钩子**一次**；**已越过**上界的会话 SHALL NOT 重复交付（避免以**已稀释**的
后继摘要覆写上一层已保存的完整内容）。会话标识为空串 SHALL NOT 交付。钩子 UNWIRED（缺省）⇒
SHALL NOT 交付，压实行为**逐字不变**。钩子抛错 SHALL **降级**（不牵连压实本身的写回与迁移，且经
`warnings.warn` 留痕，不静默吞异常）。

会话**因价值门控被跳过**时（条目取得的最高分低于阈值），系统 SHALL 经 `warnings.warn` **留痕**（只报**会话键**，SHALL NOT 回显摘要 / 事件正文 —— 承密钥红线），SHALL NOT 静默跳过。

摘要 prompt SHALL 以**同一** `MAX_SUMMARY_CHARS` 作为产出长度要求（提示词中的字数上界由该常量
派生，SHALL NOT 另设更小的固定死值）—— 提示词上界与落库上界不一致会使模型过早压缩、长任务的
最新结论更易丢失。

摘要器注入后返回**空摘要**（falsy）时，系统 SHALL 经 `warnings.warn` **留痕**（只报会话键，
SHALL NOT 回显正文），并 SHALL **跳过本轮该会话的派生抽取**（关键事实 / 关系 / 情景归纳）与
摘要提交 —— 原条目未归档、下一轮仍会成为材料，重复抽取只会以同一 trace 覆盖写并放大模型调用。
未注入摘要器时 SHALL NOT 因此跳过抽取（派生抽取与摘要提炼彼此独立，与既有行为一致）。

#### Scenario: 摘要落库前脱敏
- **GIVEN** 摘要器返回的摘要含密钥形态子串
- **WHEN** 压实写回摘要条目
- **THEN** 落库内容不含该明文（替换为 `<redacted>`），其余正文保持不变

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

#### Scenario: 循环内压实一律按本轮会话聚合
- **GIVEN** 一次携带会话标识的循环轮触发轮内压实
- **WHEN** 记忆固化执行
- **THEN** 聚合范围收窄至该会话（不聚合他会话条目），产物归该会话；全量聚合语义仅由不带会话
  标识的**显式调用**触发

#### Scenario: 摘要越界首尾保留（尾部不销毁）
- **GIVEN** 某会话既有摘要长度**超过** `MAX_SUMMARY_CHARS`
- **WHEN** 该会话再次压实、构造投喂摘要器的 prompt
- **THEN** 既有摘要槽 SHALL 含**首部**、**省略标记**与**尾部**（尾部与原文末段逐字一致），总节选长度 ≤ `MAX_SUMMARY_CHARS`；且**未越界**时 SHALL 逐字投喂全文（与变更前一致）

#### Scenario: 摘要 prompt 与上界同源
- **GIVEN** 构建摘要 prompt
- **WHEN** 检查其产出长度要求
- **THEN** 提示词中的字数上界 SHALL 等于 `MAX_SUMMARY_CHARS`（由同一常量派生），
  SHALL NOT 出现与 `MAX_SUMMARY_CHARS` 不一致的固定字数

#### Scenario: 价值门控跳过留痕（只报会话键）
- **GIVEN** 某会话条目取得的最高分低于阈值（`_below_gate` 判低价值）
- **WHEN** 压实运行并跳过该会话
- **THEN** 经 `warnings.warn` 留痕**只报会话键**（不回显摘要 / 事件正文），该会话条目层级不动

#### Scenario: 空摘要跳过派生抽取
- **GIVEN** 注入了摘要器，其对某会话返回空串，且注入了关键事实抽取器
- **WHEN** 压实该会话
- **THEN** 不写摘要、不调用派生抽取器、原条目层级不变，且以 `RuntimeWarning` 留痕该会话键

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
- **内部/派生产物豁免**：条目 `source` 属**豁免面**（`compaction` / `context` / `extraction` /
  `relation` / `episodic` —— 分别对应会话摘要与中层摘要、上下文压实产物、结构化关键事实、
  实体关系、情景归纳结论，皆由系统管道从**已准入**的材料派生）⇒ 条目 SHALL NOT 经评分
  （不拒收、不降层、不写 `importance`），其写入 SHALL 与该条目不注入评分器时**逐字一致**
  （派生结论 SHALL NOT 因评分而丢失或降层）。

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

#### Scenario: 内部派生产物豁免评分
- **GIVEN** 注入了 scorer，其对任何条目返回 0.1（低于 `IMPORTANCE_FLOOR`）
- **WHEN** 写入一条来源属豁免面（如 `source="compaction"` 的会话摘要 / 中层摘要）的派生条目
- **THEN** 条目按原意向层入库、不降层、不写 `importance`，且**无**评分留痕（派生结论不因评分而丢失）

#### Scenario: 情景归纳产物豁免评分
- **GIVEN** 注入了 scorer，其对任何条目返回 0.1（低于 `IMPORTANCE_FLOOR`）
- **WHEN** 写入一条 `source="episodic"` 的情景归纳产物
- **THEN** 条目按原意向层 L2 入库、不降层、不写 `importance`，且**无**评分留痕（派生结论不因评分而丢失）

#### Scenario: 非豁免来源（loop）仍受评分
- **GIVEN** 注入了 scorer，其对任何条目返回 0.1
- **WHEN** 写入一条来源**非**豁免面的条目（如 `source="loop"` 的轨迹条目）
- **THEN** 条目被**拒收**（不落库）、`warnings.warn` 留痕 —— 豁免面只覆盖系统派生产物

### Requirement: 记忆遗忘（forgetting）

系统 SHALL 按衰减评分（新鲜度 × 复用频次 × 重要度）识别低价值记忆并**归档**：评分低于阈值的
**L2 episodic** 条目 SHALL 迁移到 L4 归档层（**不物理删除**、`audit` 可见、检索降权），且每条
迁移 SHALL 记录可逆效应（按 trace 回滚即迁回原层）。**新鲜度衰减 SHALL 被复用信号延缓**：
条目的 freshness 衰减 SHALL 以 `freshness ** (1 / (1 + log1p(reuse_count)))` 调制——`reuse_count`
为 0 时该调制 SHALL 退化为现状（零回归锚点），复用越多衰减越缓（检索命中反哺遗忘曲线）。
**摘要类** semantic 条目（`source ∈ {compaction, context}`）、L0 元策略与 L3 技能 SHALL 不受遗忘
影响。**派生事实类** semantic 条目（`source ∈ {extraction, relation}`）SHALL **仅在**开关
`memory.semantic_forgetting` 显式开启时参与衰减归档——该开关缺省**关闭**，关闭时派生事实条目与
摘要类条目**同**不受影响（逐字回归锚点）；开启时派生事实条目的归档判据、归档去向与可撤销性
SHALL 与 episodic **同一**（同一衰减评分、同一阈值、同一 L4 归档、同一 `forgetting.<id>` 效应）。
时间戳未知（`ts<=0`）的条目 SHALL 不被惩罚。遗忘 SHALL NOT 中断 Agent 主流程。遗忘 SHALL 由
**维护节拍**驱动——循环收尾按维护间隔触发，或由显式维护入口一次性触发——而非仅依赖压实旁路；
节拍只决定"何时跑"，不改上述判据、归档去向与可撤销性。

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
- **GIVEN** L2 存在 **`source ∈ {compaction, context}` 的摘要类** `kind="semantic"` 条目，
  L0 存在人格条目，L3 存在技能条目
- **WHEN** 遗忘运行
- **THEN** 三者层级均不变（遗忘只作用于 L2 episodic 与——开关开启时的——派生事实语义条目）

#### Scenario: 遗忘可撤销
- **GIVEN** 某条目已被遗忘归档
- **WHEN** 按该条目的遗忘 trace 回滚效应
- **THEN** 条目迁回 L2 原层

#### Scenario: 开关开启时派生事实参与遗忘
- **GIVEN** 开关 `memory.semantic_forgetting` 已开启，L2 存在陈旧且从未复用的
  `source="extraction"`（或 `source="relation"`）`kind="semantic"` 条目
- **WHEN** 遗忘运行
- **THEN** 该条目迁至 L4 归档层（判据与去向同 episodic），`audit` 仍可见，且返回其撤销句柄
  `forgetting.<id>`

#### Scenario: 缺省关时派生事实不受影响
- **GIVEN** 开关 `memory.semantic_forgetting` **缺省关闭**，L2 存在陈旧且从未复用的
  `source="extraction"` `kind="semantic"` 条目
- **WHEN** 遗忘运行
- **THEN** 该条目层级保持不变（与引入该开关前**逐字一致**）

#### Scenario: 开关开启时摘要类与元策略仍不受影响
- **GIVEN** 开关 `memory.semantic_forgetting` 已开启，L2 存在陈旧且从未复用的
  `source="compaction"` 与 `source="context"` 的 `kind="semantic"` 条目，L0 存在人格条目，
  L3 存在技能条目
- **WHEN** 遗忘运行
- **THEN** 四者层级均不变（开关只放行派生事实类，摘要类与 L0/L3 恒豁免）

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

抽取 prompt 的条数要求 SHALL 与本次落库名额**同源**：注入的抽取器在未显式覆盖名额时，SHALL 按
**本次调用**聚合的 episodic 条数计算 `cap(n)` 并写入 prompt；SHALL NOT 固定为下限死值。

#### Scenario: 上限随会话长度自适应
- **GIVEN** 两次压实分别聚合 20 条与 200 条 episodic 条目
- **WHEN** keyfact 抽取落库
- **THEN** 两次压实的条数上界按 `cap(n)` 分别计算，长会话的上界不低于短会话，且均落在
  `[KEY_FACTS_MIN, KEY_FACTS_MAX]` 区间

#### Scenario: 自适应上限不低于既有死值
- **GIVEN** 任意聚合条数 n ≥ 0
- **WHEN** 计算 cap(n)
- **THEN** cap(n) ≥ 既有固定上界 `MAX_KEY_FACTS_PER_COMPACT` 的原取值（宽松化而非收紧）

未注入抽取器**或配置关闭**（`memory.key_fact_extract` = false）⇒ SHALL NOT 抽取，压实行为
（摘要写回、条目迁移、评分）**逐字不变**。配置键 `memory.key_fact_extract` SHALL 为**组合根接线闸**——
缺省 **true**（保留既有行为，不得静默停用在用能力）；显式关闭时组合根 SHALL **不**注入
`key_fact_extractor`。该键 SHALL 只决定**是否接线**，SHALL NOT 改变本条其余任何落库/脱敏/有界判据。

#### Scenario: 抽取 prompt 名额随聚合条数自适应
- **GIVEN** 注入缺省抽取器（未显式覆盖名额）
- **WHEN** 分别对 20 条与 200 条 episodic 条目构建抽取 prompt
- **THEN** 前者要求的名额 SHALL 等于 `cap(20)`（= `KEY_FACTS_MIN`），后者 SHALL 等于
  `cap(200)`（= `KEY_FACTS_MAX`）—— prompt 名额与落库名额同源

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

#### Scenario: 配置关闭 ⇒ 不接线、压实逐字不变
- **GIVEN** `memory.key_fact_extract` 显式置 **false**
- **WHEN** 组合根装配 `MemoryStore`
- **THEN** **不**注入 `key_fact_extractor`（`None`）⇒ 不产出任何 `key_fact` 条目，摘要写回 /
  条目迁移 / 评分与**未引入该键时**逐字一致

#### Scenario: 门控缺省开 ⇒ 保留既有抽取
- **GIVEN** **未**显式配置 `memory.key_fact_extract`（缺省）
- **WHEN** 组合根装配 `MemoryStore`
- **THEN** 照常注入抽取器 ⇒ 关键事实抽取行为与引入该键前**逐字一致**（缺省不改变在用能力）

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

### Requirement: 情景链（时序相邻标注）

系统 SHALL 为**情景**（`kind="episodic"` 且 `layer="L2"`）条目提供**跨轮时序结构**，
且**只**提供三件事：轮级失败条目上的**时序相邻标注**、按会话的**只读链重建**，
以及按会话的**只读失败教训读面**（见 (h)）。

**（a）时序相邻标注。** 轮级失败条目 SHALL 在其 `tags` 上承载一个值
`after:<前序 trace_id>`，其中前序 SHALL 为**同一会话内上一已记忆轮**的 `trace_id`。
该标注 SHALL NOT 新开条目、SHALL NOT 新增 `MemoryEntry` 字段（标签是既有消费面
—— `_PRESERVE_TAGS` / `exclude_fact_tags` —— 的既有惯用法，且同 `id` 幂等、
在 L2→L4 迁移中原样存活）。

**（b）语义 SHALL 为「时序相邻」，SHALL NOT 为「因果」。** 系统 SHALL NOT 推断
「后一轮的失败是由前一轮的某个动作**导致**的」。理由：仓内**不存在**确定性的因果事实，
推导它必须由模型生成**失败归因散文** —— 不可测正确性（只能测形状）、非可逆（需新增写路径）、
**新脱敏面**（模型生成的归因散文正是密钥易泄处）、且诊断面已按 `plugin_id` 归因、
时序前驱**不增加信号**。⇒ 标注值 SHALL 按**机制本名**命名（`after:`），
SHALL NOT 使用 `caused_by:` / `because:` 一类的**因果措辞**。

**（c）前序来源 SHALL 为零 I/O.** 前序 SHALL 取自循环实例内**按会话**维护的
「上一已记忆轮的 `trace_id`」，SHALL NOT 为此触发任何记忆读取 —— 读取会**强化** `reuse_count`
（构成新副作用），且底层检索返回**写序**而非 `ts` 序。

**（d）开关与逐字不变.** 标注 SHALL 由一显式开关控制（配置 `loop.causal_links`，缺省**关闭**）。
关闭 ⇒ 失败条目的 `tags` SHALL **逐字不变**（不含任何 `after:` 值）⇒ 既有行为逐字一致。
开启或关闭 SHALL NOT 改变失败条目的 `id` / `content` / `source` / `kind` / `trace_id`。

**（e）标注 SHALL NOT 意外遮蔽既有消费面.** 新标签 SHALL NOT 使失败条目
i) 逃出压实材料的**排除面**（`_PRESERVE_TAGS` 按 `failure` 标签排除，该标签 SHALL 保留）。
失败条目与「相关事实」注入面的关系 SHALL **取决于「既往失败教训」注入块是否启用**（见 (h) 与
loop「执行循环」）：该块**未启用**（缺省）时，失败条目 SHALL **仍在**事实面（该面按 `steps`
标签排除，失败条目无此标签）⇒ 既有行为**逐字不变**；该块**启用**时，失败条目 SHALL **退出**
事实面（改由教训专块承载 —— 同「压缩产物退出事实面」/「原始步序退出事实面」的
「专块承载 ⇒ 退出事实面」口径，避免同一内容两处注入）。

**（f）只读链重建.** `MemoryStore.session_chain(session_id) -> list[ChainNode]` SHALL 返回该
会话情景条目的链，按 `ts` **主序**（同 `ts` 保持写入序）；`session_id` 缺省空串 ⇒ 不按会话过滤。
该调用 SHALL 为**零效应**：SHALL NOT 强化 `reuse_count`、SHALL NOT 产生任何写入效应。
节点 SHALL 携带：条目 `id`、`trace_id`、`ts`、**失败标记**、`after` 值（无则空串）。

**（g）只读呈现面.** 只读诊断源（`core.diagnostics`）SHALL 提供一张**情景链视图**
（`render_chain`），由 TUI 只读命令族与 CLI 诊断面**共用同一产出**（诊断包 SHALL NOT 各写一份）。
该视图 SHALL 经**注入的可调用**取链（诊断包 SHALL NOT 自建 `MemoryStore`、SHALL NOT
import `core.runtime` / `core.ui`），且 SHALL 只呈现 `ChainNode` **已携带**的链路语义
—— SHALL NOT 呈现条目**正文**（节点非第二条注入通道）。视图 SHALL 保持 (f) 的**零效应**约束：
SHALL NOT 产生写入效应、SHALL NOT 强化 `reuse_count`；呈现 SHALL **有界**（单会话至多
`_MAX_CHAIN_ROWS` 节）。句柄未注入 / 链为空 ⇒ 视图 SHALL **如实降级**为一行结论，
SHALL NOT 抛异常。

**（h）只读失败教训读面.** `MemoryStore.failure_lessons(session_id, *, limit=5) -> list[MemoryEntry]`
SHALL 返回该会话的**失败条目**（`tags` 含 `failure`），按 `ts` **降序**（最近者在前）、
**至多 `limit` 条**；`session_id` 缺省空串 ⇒ 不按会话过滤。该读面 SHALL **层无关** ——
失败条目**已归档至 L4 者 SHALL 仍可读**（失败证据不因层级迁移而失联）。该调用 SHALL 为
**零效应**：SHALL NOT 强化 `reuse_count`、SHALL NOT 产生任何写入效应 —— 故 SHALL NOT 经
`read()`（后者会强化 `reuse_count` 并落盘）。该读面只供**注入**消费（渲染为推理提示块，见
loop「执行循环」），SHALL NOT 变更任何条目字段。

#### Scenario: 关闭时失败条目标签逐字不变

- **GIVEN** 标注开关**关闭**（缺省）
- **WHEN** 一轮失败被记忆
- **THEN** 该失败条目的 `tags` 恰为既有取值（`loop` + `failure`），**不含**任何 `after:` 值

#### Scenario: 开启时标注同会话的时序相邻

- **GIVEN** 标注开关**开启**，同一会话先后两轮**均失败**
- **WHEN** 读取第二轮失败条目的 `tags`
- **THEN** 其含 `after:<第一轮的 trace_id>`

#### Scenario: 标注后仍被压实材料排除

- **GIVEN** 标注开关开启且失败条目已在链上
- **WHEN** 收集压实材料（`kind="episodic"` 且 `layer="L2"`）
- **THEN** 该失败条目 **SHALL NOT** 入选（`failure` 标签仍在 ⇒ `_PRESERVE_TAGS` 仍命中）

#### Scenario: 标注后仍进「相关事实」注入面

- **GIVEN** 标注开关开启且该注入面按 `steps` 标签排除原始行动序列
- **WHEN** 装配本轮事实
- **THEN** 失败条目 **SHALL** 仍在事实面（其 `tags` 不含 `steps`）

#### Scenario: 只读链按序、跨会话不混、零效应

- **GIVEN** 两个会话各自写入若干情景条目（交错）
- **WHEN** 以其中一个会话调用 `session_chain`
- **THEN** 只得到该会话的条目、按 `ts` 不减排列；且调用前后各条目的 `reuse_count` **不变**、
  效应追踪器**无新增记录**

#### Scenario: 只读诊断面呈现链

- **GIVEN** 诊断源注入了链句柄（该会话有失败轮，且失败轮带 `after:` 标注）
- **WHEN** 渲染 `render_chain`（TUI 只读命令族同一产出）
- **THEN** 呈现含该会话的**失败标记**与 `after` 值；且调用前后 store **无新增写入效应**、
  `reuse_count` **不变**

#### Scenario: 句柄未注入或空链时不抛

- **GIVEN** 诊断源**未**注入链句柄，或注入的链为空
- **WHEN** 渲染 `render_chain`
- **THEN** 分别得到「未接线」/「（空）」一行结论，SHALL NOT 抛异常

#### Scenario: 只读失败教训按会话、有界、降序、零效应

- **GIVEN** 两个会话各自写入若干失败条目（其中一条已归档至 L4），交错写入
- **WHEN** 以其中一个会话调用 `failure_lessons(session_id, limit=2)`
- **THEN** 只得到该会话的失败条目、按 `ts` 递减排列、至多 2 条，且已归档者也含于其中；
  调用前后各条目的 `reuse_count` **不变**、效应追踪器**无新增记录**

#### Scenario: 启用教训块时失败条目退出事实面

- **GIVEN** 「既往失败教训」注入块**启用**，且某失败条目在库
- **WHEN** 装配本轮事实（`exclude_fact_tags` 含 `failure`）
- **THEN** 该失败条目 **SHALL NOT** 出现在「相关事实」块（其信息由教训专块承载）

#### Scenario: 未启用教训块时失败条目仍在事实面

- **GIVEN** 「既往失败教训」注入块**未启用**（缺省）
- **WHEN** 装配本轮事实
- **THEN** `exclude_fact_tags` **不含** `failure` ⇒ 失败条目**仍在**事实面，
  行为与引入本能力前**逐字一致**

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

关系抽取 prompt 的条数要求 SHALL 与 `relation_cap(n)` **同源**（同上：未显式覆盖时按本次聚合
条数计算）；谓词表 SHALL 由闭合白名单**派生**并展示每个规范谓词的中英变体（至少全部中文变体），
SHALL NOT 另写第二份词表 —— 纯中文会话须能直接选词。

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

#### Scenario: 关系 prompt 名额随聚合条数自适应
- **GIVEN** 注入缺省关系抽取器（未显式覆盖名额）
- **WHEN** 分别对 20 条与 200 条 episodic 条目构建关系抽取 prompt
- **THEN** 前者要求的名额 SHALL 等于 `relation_cap(20)`，后者 SHALL 等于 `relation_cap(200)`

#### Scenario: 关系 prompt 展示中英变体
- **GIVEN** 构建关系抽取 prompt
- **WHEN** 检查谓词表
- **THEN** 每个规范谓词及其**全部中文变体** SHALL 出现；谓词表 SHALL 由归一化白名单派生
  （变体集合恒等）

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

### Requirement: 记忆后端落盘耐久（backend durability）
系统 SHALL 保证文件记忆后端（`memory.jsonl`）的落盘耐久：持久化写入 SHALL 为**原子提交**
（先写临时文件再原子替换——写入中途被中断 SHALL NOT 损坏或清空既有条目集合）；加载 SHALL
对**逐行损坏容错**（半行/坏行 SHALL 被跳过并记录告警，SHALL NOT 阻断启动，完好行不受影响）。
告警 SHALL 只报损坏行计数，SHALL NOT 回显条目内容。本要求为**缺陷修复**（既有行为：半写 ⇒
下次启动 `build_runtime` 直接抛异常），故**缺省生效**、无开关。

- **原子性**：写入失败点若落在持久化路径上，既有条目集合 SHALL 保持完整（可重载、可续用）。
- **逐行容错**：单行损坏 SHALL NOT 使整个后端不可用（与 durability「检查点损坏降级」同口径：
  不因单点损坏阻塞启动）。
- **告警不回显**：损坏告警只含计数与文件名，SHALL NOT 含条目正文（条目可能含敏感内容）。

#### Scenario: 半写不损坏既有条目
- **GIVEN** 文件后端已持久化条目集合，且一次持久化写入在中途被中断（写到一半失败）
- **WHEN** 重新加载存储
- **THEN** 既有条目集合不受影响（不出现部分覆盖或整体丢失），完好条目仍可读

#### Scenario: 坏行跳过不阻断启动
- **GIVEN** `memory.jsonl` 含半行（非法 JSON）与结构不符行（非条目形状的合法 JSON），间杂完好行
- **WHEN** 构造文件后端（启动路径）
- **THEN** 启动不被阻断，完好条目全部可读，损坏行被跳过且记录告警（只报计数，不回显内容）

#### Scenario: 完好文件往返逐字节不变
- **GIVEN** 一个只含完好行的 `memory.jsonl`
- **WHEN** 重载后再触发一次持久化
- **THEN** 落盘字节与重载前逐字节一致（既有行为零回归锚）

#### Scenario: 真实进程崩溃后重载可读
- **GIVEN** 一个进程在完成记忆写入后被 `SIGKILL` 终止
- **WHEN** 另一进程重载同一落盘文件
- **THEN** 已持久化条目全部可读，无告警（原子替换 ⇒ 无半写残留）

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
