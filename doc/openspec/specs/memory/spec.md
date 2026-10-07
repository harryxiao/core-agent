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

### Requirement: 记忆遗忘（forgetting）
系统 SHALL 按衰减评分（新鲜度 × 复用频次 × 重要度）识别低价值记忆并**归档**：评分低于阈值的
**L2 episodic** 条目 SHALL 迁移到 L4 归档层（**不物理删除**、`audit` 可见、检索降权），且每条
迁移 SHALL 记录可逆效应（按 trace 回滚即迁回原层）。semantic 条目、L0 元策略与 L3 技能 SHALL
不受遗忘影响；时间戳未知（`ts<=0`）的条目 SHALL 不被惩罚。遗忘 SHALL NOT 中断 Agent 主流程。
遗忘 SHALL 由**维护节拍**驱动——循环收尾按维护间隔触发，或由显式维护入口一次性触发——
而非仅依赖压实旁路；节拍只决定"何时跑"，不改上述判据、归档去向与可撤销性。

#### Scenario: 低分条目归档
- **GIVEN** 一条陈旧且从未复用的 L2 episodic 条目
- **WHEN** 遗忘运行
- **THEN** 该条目迁至 L4 归档层，`audit` 仍可见，且返回其撤销句柄

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
