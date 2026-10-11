# Memory Specification Delta — 滚动摘要首尾保留（change 0193）

## MODIFIED Requirements

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

#### Scenario: 价值门控跳过留痕（只报会话键）
- **GIVEN** 某会话条目取得的最高分低于阈值（`_below_gate` 判低价值）
- **WHEN** 压实运行并跳过该会话
- **THEN** 经 `warnings.warn` 留痕**只报会话键**（不回显摘要 / 事件正文），该会话条目层级不动
