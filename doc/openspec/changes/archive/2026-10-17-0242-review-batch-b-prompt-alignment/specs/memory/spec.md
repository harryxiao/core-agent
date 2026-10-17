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
