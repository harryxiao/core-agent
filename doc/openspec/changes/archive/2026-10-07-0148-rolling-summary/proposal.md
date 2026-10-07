# 0148 · 记忆压实「增量滚动摘要」（账本 E90）

> 账本：`coding-plan/known-risk.md` **E90**（本轮立账后实施）
> 规格面：`memory` MODIFIED「记忆压实」（新增 Scenario「滚动合并既有摘要（不丢失）」）
> ADR：**0140** ｜ 来源：外部参考件 `Agent-Memory.md` 审查 ⇒ **取精华弃糟粕**

## Why

审查外部参考件 `Agent-Memory.md`（本地 Agent 长对话记忆压缩方案）后立账 `E90`/`E91`/`E92`。
**`E90` 是唯一会真实损害长会话质量**的项：当前记忆摘要为「**批式重提炼 + 固定 id 原地覆盖**」，
**不是**参考方案的「现有摘要 + 新片段 → 合并」。

**根因（三处，均在 `src/core/memory/`）**：

1. `store.py:369` `_episodic_groups()` **只收 `kind=="episodic"`** ⇒ 旧摘要（`kind=="semantic"`）
   **不进 prompt**；
2. `store.py:391` 摘要 **id 写死** `compaction.summary.<key>` ⇒ 新一轮摘要**原地覆盖**上一轮；
3. 被覆盖的原摘要所引条目**已迁 L4**（`store.py:401-402`）⇒ **长会话早期结论逐轮稀释直至丢失**。

且该行为已被**接口文档写成明文契约**（`03-interfaces/memory-interface.md` §3「摘要式压实」表：
`id` = `compaction.summary.<session_id>`「同会话重复压实为**覆盖**，不增长」）⇒ 本 change 是
**规格 + 接口双重口径**变更。

## What

全部为增量，既有语义逐字不动：

1. `memory/summarize.py`：新增常量 `_MAX_SUMMARY_CHARS = 2000`（**既有摘要**的节选上界；
   `_MAX_ENTRY_CHARS = 400` 只管**新事件**）；`build_prompt` 把既有摘要条目渲染为显式
   「现有摘要」槽位，其余条目仍逐条渲染。
2. `memory/store.py`：`_summarize_sessions` 投喂前取该会话既有摘要条目，组成
   `material = [prior, *entries]`（无既有摘要则**逐字等于** `entries`）⇒ `summarizer(material)`；
   `_commit_summary` 的第二参**仍只传本轮 `entries`** ⇒ 既有摘要**只被吸收、不被迁 L4**。
3. `Summarizer` **契约不变**（`Callable[[list[MemoryEntry]], str]`，不新增形参）⇒
   `runtime.py` 的 `summarize_with(_llm_text)` 装配与 `MemoryStore.__init__` **零改动**。

## 影响

- **早期结论不再丢失**：摘要沿会话**滚动累积**（融合既有结论与新增事实）。
- **条目数不变**：仍为每会话至多一条摘要条目、`id` 不变（滚动的是**内容**，不是条目数）。
- **零回归**：既有 `tests/test_memory.py` 对摘要器输入的断言（`seen == [["e0","e1"],["e2"]]` 等）
  全部是「**首次压实**」（无既有摘要）⇒ 新实现「无既有摘要 ⇒ 材料逐字等于 `entries`」下原样通过。
- **既有语义保持**：按会话收窄、价值门控、可撤销、未注入摘要器降级 —— **逐字不动**。

## 非目标（明确不做）

- **版本化摘要 id / 把旧摘要迁 L4**：与接口「每会话至多一条、不增长」口径冲突，且徒增条目。
- **改 `write()` 的 undo 语义（覆盖写可单轮回滚）**：超出本账；压实效应共用
  `trace_id=f"compaction.<key>"` ⇒ 回滚恒为**该会话全量**一并逆转，与规格「压实可撤销」一致 ⇒ 非缺陷。
- **M4 结构化抽取（`E92`）/ M5 工具说明按需注入（`E91`）/ M8 高保真标记**：本次不做，已立账另议。
- **参考方案代码照搬**：其 `key_facts` **明文密钥** Schema 与本仓库红线冲突，一律不取。

## 验证

- `.venv/bin/ruff check src tests` / `ruff format --check` 全绿；`pyright` **0/0/0**。
- `.venv/bin/pytest -q` ⇒ 基线 + 本 change 新增（`tests/test_memory.py`：T1/T2/T3 三条 +
  T5 一条）；T1/T2/T3 **实现前红**、实现后绿；既有 memory 用例**逐字不动**全绿。
- `openspec validate --all` ⇒ 31 passed / 0 failed（归档后 30/0）。

## 风险与已知局限

- **覆盖写不支持单轮回滚**：压实效应共用 `trace_id`，回滚为**该会话全量**（既有口径，非本次引入）
  ⇒ 记 ADR-0140 已知局限。
- **既有摘要超 `_MAX_SUMMARY_CHARS` 即被截断**：有界优先（token 有界）。
- **摘要质量取决于注入模型**：未注入则降级不写（既有行为）。
