# memory — 跨进程落盘合并与遗忘检索隔离（change 0301）

## MODIFIED Requirements

### Requirement: 记忆后端落盘耐久（backend durability）

系统 SHALL 保证文件记忆后端（`memory.jsonl`）的落盘耐久：持久化写入 SHALL 为**原子提交**
（先写临时文件再原子替换——写入中途被中断 SHALL NOT 损坏或清空既有条目集合）；加载 SHALL
对**逐行损坏容错**（半行/坏行 SHALL 被跳过并记录告警，SHALL NOT 阻断启动，完好行不受影响）。
告警 SHALL 只报损坏行计数，SHALL NOT 回显条目内容。本要求为**缺陷修复**（既有行为：半写 ⇒
下次启动 `build_runtime` 直接抛异常），故**缺省生效**、无开关。

**跨进程合并**（change `0301`）：持久化 SHALL 在**独占建议锁**内先读取盘上最新集合，再按
**本次变更集**（新增/覆盖的条目 id 与删除的 id）合并，SHALL NOT 用进程启动时的内存快照整体
覆盖盘上文件；锁取不到（fail-open）SHALL 退化为无锁写入（SHALL NOT 让记忆写入成为新的失败面）。
合并落盘后进程内集合 SHALL 采纳盘上最新集合（其他进程写入的条目对本进程可见）；删除 SHALL
只移除指定 id，SHALL NOT 复活其他进程已删除的条目。本项同样**缺省生效**、无开关。

- **原子性**：写入失败点若落在持久化路径上，既有条目集合 SHALL 保持完整（可重载、可续用）。
- **逐行容错**：单行损坏 SHALL NOT 使整个后端不可用（与 durability「检查点损坏降级」同口径：
  不因单点损坏阻塞启动）。
- **告警不回显**：损坏告警只含计数与文件名，SHALL NOT 含条目正文（条目可能含敏感内容）。
- **跨进程不覆盖**：两个后端实例分别写入不同条目后，重载 SHALL 同时看到两者；任一实例的
  读取强化写回 SHALL NOT 丢弃另一实例在期间写入的条目。

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

#### Scenario: 跨实例写入合并
- **GIVEN** 两个后端实例指向同一落盘文件（模拟两个进程），其一先写入条目 A
- **WHEN** 另一实例写入条目 B 并重新加载
- **THEN** A 与 B 同时存在于落盘集合中（后写者 SHALL NOT 用启动时快照覆盖先写者）

#### Scenario: 读取强化不覆盖他进程写入
- **GIVEN** 实例甲已加载集合，实例乙随后写入新条目 C
- **WHEN** 实例甲经检索选中既有条目并触发复用强化落盘
- **THEN** C 仍存在于落盘集合，且被强化条目的 `reuse_count` 已更新

#### Scenario: 删除只作用于目标条目
- **GIVEN** 实例乙删除了条目 A，实例甲随后写入条目 C
- **WHEN** 两个实例分别重新加载
- **THEN** A 保持删除、C 与其余条目均在（删除 SHALL NOT 被快照复活）

#### Scenario: 锁不可用仍可写入
- **GIVEN** 锁文件路径不可用（如被目录占用）
- **WHEN** 后端持久化写入
- **THEN** 写入照常完成（fail-open：无锁降级，SHALL NOT 抛错或丢弃条目）

### Requirement: 记忆遗忘（forgetting）

系统 SHALL 按衰减评分（新鲜度 × 复用频次 × 重要度）识别低价值记忆并**归档**：评分低于阈值的
**L2 episodic** 条目 SHALL 迁移到 L4 归档层（**不物理删除**、`audit` 可见），且每条迁移 SHALL
记录可逆效应（按 trace 回滚即迁回原层）；迁移的**同时** SHALL 为该条目标注 `forgotten` 标签
（同一 trace 可回滚）。带 `forgotten` 标签的条目 SHALL **退出所有注入面**——事实检索
（`read()`）与失败教训读面（`failure_lessons()`）缺省 SHALL NOT 返回；审计（`audit()`）与
诊断（`session_chain()`）读面 SHALL 仍可见（墓碑语义：保留追溯、停止召回）；显式
`read(include_forgotten=True)` SHALL 可查看。**新鲜度衰减 SHALL 被复用信号延缓**：
条目的 freshness 衰减 SHALL 以 `freshness ** (1 / (1 + log1p(reuse_count)))` 调制——`reuse_count`
为 0 时该调制 SHALL 退化为现状（零回归锚点），复用越多衰减越缓（检索命中反哺遗忘曲线）。
**摘要类** semantic 条目（`source ∈ {compaction, context}`）、L0 元策略与 L3 技能 SHALL 不受遗忘
影响。**派生事实类** semantic 条目（`source ∈ {extraction, relation}`）SHALL **仅在**开关
`memory.semantic_forgetting` 显式开启时参与衰减归档——该开关缺省**关闭**，关闭时派生事实条目与
摘要类条目**同**不受影响（逐字回归锚点）；开启时派生事实条目的归档判据、归档去向与可撤销性
SHALL 与 episodic **同一**（同一衰减评分、同一阈值、同一 L4 归档、同一 `forgotten` 标签、同一
`forgetting.<id>` 效应）。时间戳未知（`ts<=0`）的条目 SHALL 不被惩罚。遗忘 SHALL NOT 中断
Agent 主流程。遗忘 SHALL 由**维护节拍**驱动——循环收尾按维护间隔触发，或由显式维护入口一次性
触发——而非仅依赖压实旁路；节拍只决定"何时跑"，不改上述判据、归档去向与可撤销性。

#### Scenario: 低分条目归档
- **GIVEN** 一条陈旧且从未复用的 L2 episodic 条目
- **WHEN** 遗忘运行
- **THEN** 该条目迁至 L4 归档层、`tags` 含 `forgotten`，`audit` 仍可见，且返回其撤销句柄；
  缺省 `read()` 不再返回该条目

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
- **GIVEN** 某条目已被遗忘归档（带 `forgotten` 标签）
- **WHEN** 按该条目的遗忘 trace 回滚效应
- **THEN** 条目迁回 L2 原层、`forgotten` 标签被移除，且缺省 `read()` 重新返回该条目

#### Scenario: 遗忘条目退出全部注入面
- **GIVEN** 一条带 `failure` 标签的条目已被遗忘归档（同会话）
- **WHEN** 以该会话执行事实检索与 `failure_lessons()`
- **THEN** 两者均不返回该条目；`audit()` 仍返回它（墓碑可追溯）

#### Scenario: 显式包含遗忘条目可见
- **GIVEN** 一条已被遗忘归档的条目
- **WHEN** 以 `read(..., include_forgotten=True)` 检索
- **THEN** 该条目可被返回（显式回溯面），且其层级仍为 L4、标签仍含 `forgotten`

#### Scenario: 非遗忘归档仍可召回
- **GIVEN** 一条因**压实**迁至 L4 的条目（`tags` 不含 `forgotten`）
- **WHEN** 以缺省 `read()` 检索命中它
- **THEN** 该条目仍可被返回（归档 ≠ 遗忘；本能力的排除只认 `forgotten` 标签）

#### Scenario: 开关开启时派生事实参与遗忘
- **GIVEN** 开关 `memory.semantic_forgetting` 已开启，L2 存在陈旧且从未复用的
  `source="extraction"`（或 `source="relation"`）`kind="semantic"` 条目
- **WHEN** 遗忘运行
- **THEN** 该条目迁至 L4 归档层（判据与去向同 episodic）、`tags` 含 `forgotten`，`audit` 仍
  可见，且返回其撤销句柄 `forgetting.<id>`

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
失败条目**已归档至 L4 者 SHALL 仍可读**（失败证据不因层级迁移而失联）；**例外**：带
`forgotten` 标签（已遗忘）者 SHALL NOT 返回（遗忘优先于教训可见性，其审计仍可经 `audit()`）。
该调用 SHALL 为**零效应**：SHALL NOT 强化 `reuse_count`、SHALL NOT 产生任何写入效应 —— 故
SHALL NOT 经 `read()`（后者会强化 `reuse_count` 并落盘）。该读面只供**注入**消费（渲染为推理
提示块，见 loop「执行循环」），SHALL NOT 变更任何条目字段。

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

#### Scenario: 已遗忘的失败条目不被教训读面返回

- **GIVEN** 该会话的一条失败条目已被遗忘归档（`tags` 含 `forgotten`）
- **WHEN** 调用 `failure_lessons(session_id)`
- **THEN** 不返回该条目；`audit()` 仍可查得它（墓碑可追溯）

#### Scenario: 启用教训块时失败条目退出事实面

- **GIVEN** 「既往失败教训」注入块**启用**，且某失败条目在库
- **WHEN** 装配本轮事实（`exclude_fact_tags` 含 `failure`）
- **THEN** 该失败条目 **SHALL NOT** 出现在「相关事实」块（其信息由教训专块承载）

#### Scenario: 未启用教训块时失败条目仍在事实面

- **GIVEN** 「既往失败教训」注入块**未启用**（缺省）
- **WHEN** 装配本轮事实
- **THEN** `exclude_fact_tags` **不含** `failure` ⇒ 失败条目**仍在**事实面，
  行为与引入本能力前**逐字一致**
