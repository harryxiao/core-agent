# Proposal 0202 — 情景链（时序相邻标注）

## 为什么

外部蓝图（`memory-4-layer-architecture.md` §4.2）要求情景记忆做「时序建模 + 因果分析」。
本仓现状：每轮的三个条目（`loop.<trace>` / `loop.steps.<trace>` / `loop.failure.<trace>`）
共享**同一个** `trace_id` ⇒ 只表达**同轮隐式**关联；**跨轮关系为零**，且**没有**任何按会话
重建时序链的读取面。⇒ 情景层有**轮内**结构、缺**跨轮**结构。

**诚实评估先行（写入 ADR-0192）**：仓内**不存在**确定性的因果事实 —— 没有任何环节记录
「第 N+1 轮失败是因第 N 轮做了什么」。推导它**必须靠 LLM 推断**，而 LLM 推断在此有四个问题：
**不可测正确性**（只能测形状）、**非可逆**（需新增写路径）、**新脱敏面**（模型生成的失败归因
散文正是密钥易泄处）、**无消费者增量**（`Diagnoser` 已按 `plugin_id` 归因，时序前驱不增加信号）。
⇒ **不做 LLM 因果推断**（同 ADR-0041 的拒绝先例）。只做**确定性**的两件事。

## 做什么

1. **跨轮时序相邻标注**：轮级失败条目 `tags` 增加一个值 **`after:<前序 trace_id>`** ——
   前序 = **同会话内上一已记忆轮**的 `trace_id`，取自 `DefaultLoop` 进程内**按会话**维护的
   `self._last_trace`（`remember` 只有一个调用点，一处维护）。**零记忆读** ⇒ 零新副作用
   （读数会强化 `reuse_count`，而 `MemoryBackend.search("")` 返回**写序**而非 `ts` 序）。
2. **零效应只读链**：`MemoryStore.session_chain(session_id) -> list[ChainNode]` —— 按 `ts` 主序
   （同 `ts` 保写入序）重建该会话情景链；节点带 条目 id / `trace_id` / `ts` / 失败标记 / `after` 值。
3. 配置 `loop.causal_links`（缺省 **`False`**）+ `DefaultLoop(causal_links=False)` 构造参 +
   组合根注入四只 loop。

## 命名裁决

标签名为 **`after:`**（时序相邻），**不是** `caused_by:` —— 沿 ADR-0173「按机制本名命名」先例。
本 change 的名称与**规格要求标题**同样只声称**时序相邻**（原批次名「因果链」是**缺口名**，
不是**交付名**）；「不做因果推断」作为 SHALL NOT 写进规格。

## 存储决策（真抉择 —— 为什么不新开条目 / 不加字段）

- **独立条目** `loop.cause.<tid>`：否 —— 每次失败多一次写入换一个字符串，且会作为 `episodic`
  L2 进入压实材料。
- **新增 `MemoryEntry` 字段**：否 —— `MemoryEntry` 是跨 `MemoryBackend` 的**线上形状**，
  `FileBackend` 持久化需迁移。
- **标签** —— **采纳**：同 `id` 幂等、`forget` 的 L2→L4 迁移原样存活、零 schema 变更，
  且**消费面本就是标签驱动**（`_PRESERVE_TAGS` / `exclude_fact_tags` / `assembler._shares_any_tag`）。

## 两处必须断言的交互（新标签 SHALL NOT 意外遮蔽）

- `_PRESERVE_TAGS`（`frozenset({"failure"})`）：`tags` **仍含** `failure` ⇒ `_episodic_groups`
  **仍排除**该条目 ⇒ 压实材料面**未受扰动**。
- `exclude_fact_tags`（生产值 `frozenset({"steps"})`）：失败条目**无** `steps` 标签 ⇒
  **仍进**「相关事实」注入面。

## 不改什么

- 失败条目的 `content` / `id` / `source` / `kind` **逐字不变**（只可能多一个 `tags` 值）。
- 不新增条目、不改 `MemoryEntry`、不改 `MemoryBackend`、不改 `MemoryStore.read` 的检索语义。
- **不接线** `Diagnoser(predecessor_lookup=…)` —— 那要求对 `evolution/spec.md`「对比诊断」做
  约 36 行逐字 MODIFIED（本批最高风险的规格编辑），而用户裁决的选项只要求 `session_chain`
  读取面 ⇒ **登记为遗留**，不并入本 change。

## 规格影响

`memory` **ADDED** 一条要求「情景链（时序相邻标注）」（5 Scenario）。既有 13 条 Requirement
**逐字保留**（不做 MODIFIED）；`loop` 规格**零改动**（实现面在 `loop`，但 `loop` 规格已由
「无行动不记忆」覆盖记忆写入，本 change 不新增其义务）。

## 风险

- **标签泄漏成因果**：标签若被读成因果，会误导诊断。⇒ 规格 SHALL NOT 明令「因果不作推断」，
  ADR 记「不自洽的因果声明比没有更坏」。
- **进程内前序表**：跨进程重启、以及 main/sub/beast 三路 loop 实例之间**链路会断** ⇒
  **如实登记**为局限（只读面以 `ts` 为主序、写序为次序）。
- **开关语义**：关闭 ⇒ 无 `after:` 值 ⇒ 失败条目**逐字不变**（反证：忽略开关 ⇒ 逐字锚转红）。
