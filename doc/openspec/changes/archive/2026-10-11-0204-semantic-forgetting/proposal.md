# Proposal 0204 — 语义遗忘面（派生事实参与遗忘，摘要类永久豁免）

## 为什么

「四类记忆是否闭环」取证确认：**语义记忆缺遗忘**。`MemoryStore.forget()` 的守卫
（`store.py:622`）是 `entry.kind != "episodic" or entry.layer != "L2" ⇒ continue`，
`kind="semantic"` 条目**永不遗忘**。

这不是实现疏漏，而是**规格写死的**：`doc/openspec/specs/memory/spec.md:391-392` 的
「记忆遗忘」SHALL 明文「**semantic 条目**、L0 元策略与 L3 技能 SHALL 不受遗忘影响」，且有一条
Scenario `提炼产物与元策略不被遗忘`（`spec.md:423-426`）断言其不变。

后果：结构化抽取落下的 `keyfact.*`（`source="extraction"`）与 `relation.*`（`source="relation"`）
条目**只增不减** —— 时间越久，噪音越大，且 `read()`/`_gather_facts` 无层过滤（L4 仅加性降权）
⇒ 陈旧派生事实**持续占注入预算**。

## 做什么

**只做一件事**：把 `记忆遗忘` 的豁免面从「**全部** semantic」收窄为「**摘要类** semantic
（`source ∈ {compaction, context}`）」，并让「**派生事实类** semantic
（`source ∈ {extraction, relation}`）」在一个**缺省关闭**的开关下参与**同一**衰减归档。

- 用户裁决（②）：**仅派生事实，摘要豁免** —— 会话摘要/中层摘要/压实产物是「已准入材料的派生
  结论」，遗忘它们会丢失记忆的骨架；派生事实（实体/关系三元组）是可再抽取、可衰减的**细节层**。
- 用户裁决（④）：**缺省关、显式开启** —— 既有路径逐字不变（沿 `0181`/`0202`/`0203` 先例）。

## 关键决策：为什么是「收窄豁免」而不是「新开遗忘面」

- **复用同一判据**：派生事实的归档仍走 `_decay_score`（新鲜度 × 复用 × 重要度）+ 同阈值
  `_FORGET_THRESHOLD` + `migrate` → L4 + `forgetting.<id>` 效应 ⇒ **零新评分逻辑、零新去向、
  零新撤销面**。改动面仅**一处布尔守卫**。
- **不新增配置面「遗忘什么」**：配比/判据面不加键（纪律，同 `0201`）。开关只表达「开不开」，
  不表达「多老算老」。
- **`forget()` 签名不动** ⇒ `loop/default.py` / `entry.py` 三处零参调用点逐字不变。

## 规格影响

`memory` **MODIFIED** 一条要求「记忆遗忘（forgetting）」—— 把「semantic 条目 SHALL 不受影响」
收窄为「**摘要类** semantic SHALL 不受影响 + **派生事实类** semantic 仅在开关开启时参与」；
同块内 **MODIFIED** 一条 Scenario `提炼产物与元策略不被遗忘`（标题不动、GIVEN 收窄），并 **ADD
3 Scenario**。canonical Requirement 数**不变**（15），Scenario **108 → 111（+3）**。
其余 14 条 Requirement **逐字保留**。

## 风险

- **误删有用事实**：开关缺省关 ⇒ 默认零风险。开启后归档的仍是「衰减评分低于阈值」的条目
  —— 与 episodic 同一门槛（≈19 天零复用零重要度）。
- **语义事实是全局层**：`keyfact.*`/`relation.*` 的 `session_id=""` ⇒ 归档**不**使其退出跨会话
  注入（与 episodic 遗忘同一既有语义，如实登记为局限，本 change 不动注入面）。
- **MODIFIED 是本仓最高风险的规格编辑类型**：只能靠 `openspec validate` + 手工归档断言
  （0 Requirement-header 丢失 / 0 Scenario-title 丢失）兜底。
