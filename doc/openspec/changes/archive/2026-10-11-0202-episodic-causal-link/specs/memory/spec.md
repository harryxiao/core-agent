# Memory Specification Delta — 情景链（change 0202）

## ADDED Requirements

### Requirement: 情景链（时序相邻标注）

系统 SHALL 为**情景**（`kind="episodic"` 且 `layer="L2"`）条目提供**跨轮时序结构**，
且**只**提供两件事：轮级失败条目上的**时序相邻标注**，以及按会话的**只读链重建**。

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
i) 逃出压实材料的**排除面**（`_PRESERVE_TAGS` 按 `failure` 标签排除，该标签 SHALL 保留），
亦 SHALL NOT 使 ii) 被挡在「相关事实」注入面之外（该面按 `steps` 标签排除，失败条目无此标签）。

**（f）只读链重建.** `MemoryStore.session_chain(session_id) -> list[ChainNode]` SHALL 返回该
会话情景条目的链，按 `ts` **主序**（同 `ts` 保持写入序）；`session_id` 缺省空串 ⇒ 不按会话过滤。
该调用 SHALL 为**零效应**：SHALL NOT 强化 `reuse_count`、SHALL NOT 产生任何写入效应。
节点 SHALL 携带：条目 `id`、`trace_id`、`ts`、**失败标记**、`after` 值（无则空串）。

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
