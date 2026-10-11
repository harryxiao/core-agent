# 情景归纳（episodic consolidation）—— change 0218

## Why

四类记忆的专属沉淀 prompt 存在**强度不对称**：程序类有 `skills.sop.build_sop_prompt`、
语义类有 `memory.extract.build_extract_prompt` / `build_relation_prompt`，而**情景类**没有自己的
沉淀 prompt —— 它复用通用的**会话摘要** prompt（`memory.summarize`）。

复用带来的**实质问题**不是「少写了一段提示词」，而是**两路语义被同一文本压平**：

1. **材料口径不同** —— 摘要器把「既有摘要」当**滚动合并**输入（既有结论 + 新事件 → 更新后的
   摘要），归纳器只想看本批事件；
2. **副作用不同** —— 摘要器**迁移**来源条目（`_commit_summary` 把原 episodic 迁 L4 归档），
   归纳器（本 change）**不迁移**任何条目，只追加一条全局层的归纳结论；
3. **产物去向不同** —— 摘要进「相关事实」面并被滚动覆盖；归纳是**面向会话的结论快照**，
   供跨会话回看「这段任务到底做成了什么」。

三者混在一条 prompt 里，任何一处措辞调整都会**同时**改变两路行为 —— 没有隔离，就无法为
情景类单独演进（P3 进化局部化与可归因）。

## What Changes

- **新增** `src/core/memory/episodic.py`（镜像 `extract.py` 三段式形状，但契约返回**文本**同
  `summarize_with`）：`EpisodicExtractor` 契约别名 ＋ `_PROMPT_HEAD`（四段结构：目标 / 经过 /
  结果 / 教训）＋ `build_episodic_prompt(entries)` ＋ `consolidate_with(llm)`。
- `MemoryStore` 新注入接缝 `episodic_extractor`（镜像 `key_fact_extractor`，缺省 UNWIRED）。
- 新内部方法 `_consolidate_episodic(session_id, entries)`：与摘要 / 关键事实 / 关系**同材料、
  同 trace、同门控**，挂进 `_summarize_sessions` 的会话循环。
- 新条目形状：`id=episodic.<key>`（每会话至多一条、覆盖式）、`source="episodic"`、
  `tags=["episodic", "session:<key>"]`、`trace_id=compaction.<key>`（回滚免费获得）、
  **`kind="semantic"`**（★ 承重：`_episodic_groups` 只收 `kind=="episodic"` ⇒ 归纳产物**不回喂**
  摘要器，避免自激环）、`session_id=""`（全局层，同关键事实 / 关系）。
- `compact()` 的「是否有事可做」守卫增加一项（注入归纳器也算有事可做）。
- 组合根 `runtime.py` 接线，键 `memory.episodic_extract`（bool，**缺省 False**）。
- store 侧**无条件** `redact_secrets` ＋ 截断至有界长度（归纳器**不构成信任边界**）。

## Impact

- **规格**：`memory` **ADDED**「情景归纳（episodic consolidation）」＋ 6 Scenario（既有 16
  Requirement 逐字保留）。
- **代码**：`src/core/memory/{episodic.py（新）,store.py,__init__.py}`、
  `src/core/configuration/manager.py`、`src/core/runtime.py`。
- **测试**：新 `tests/test_memory_episodic.py`（约 18 条）。
- **缺省关** ⇒ 未配置时压实路径**逐字不变**（无归纳器 ⇒ 不构造、不落条目）。

## 显式不做

- 不给会话摘要 / SOP / 编排 / RAG 补门控键（用户裁决「只补关键事实抽取」，本批已由 `0216` 覆盖）。
- **不**把新 `source="episodic"` 登记进 `_GATE_EXEMPT_SOURCES` / `_FORGETTABLE_SEMANTIC_SOURCES`
  —— 与 `importance_gate` 同开时该条目会过闸、且恒豁免遗忘；登记为**后续候选**（本轮保最小
  爆炸半径）。见 ADR-0208 局限 ①。
- 不改造现有会话摘要 prompt（用户裁决「新增独立情景归纳器」）。
- 不给归纳条目做机读结构化（自由文本，供人读 / 供注入）。
