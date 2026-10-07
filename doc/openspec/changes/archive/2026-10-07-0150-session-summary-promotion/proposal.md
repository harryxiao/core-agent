# 会话摘要提升（session summary promotion）· change 0150 · 账本 E94

## 为什么

`coding-plan/known-risk.md` **E94**：change `0148`（记忆压实滚动摘要）后，摘要**滚动累积**，但回喂既有
摘要按 `_MAX_SUMMARY_CHARS = 2000` **取前 2000 字（旧端）** ⇒ 长时程下**早期硬约束缓慢稀释**
（ADR-0140 局限②）。缓解物**已有**（`notes` 覆盖式真相层**不参与压实** + L0 宪法 + 信息地图 pointers），
但「重要结论 / 硬约束**提升进 notes**」**只靠技能纪律 `skills.notes.consult_build_update` 自觉，
无强制、无触发点** ⇒ 长任务早期硬约束可能**不落 canonical**。

与 `E90`（change `0148` 已修）**同源不同层**：E90 修「摘要**内**稀释」，E94 补「摘要 → canonical 提升」。
前置 **change `0149` / ADR-0141**（常驻 pinned 笔记）**已落地**（ADR-0141 背景已明文预留 E94 = change
`0150` / ADR-0142，**依赖** 0149）。

## 改什么

新增**显式提升路径** —— `core-agent notes promote <session-id> [--as <note_id>] [--title <title>]`：
把该会话的**压实摘要**读回（`MemoryStore.summary_for`），**覆盖式**落成一篇 canonical note，并
**自动置常驻**（`pinned=True`，每轮无条件注入）。

- **触发 = 显式（CLI 动词）**，**零 LLM 调用**、**零噪音**、**不污染全局 notes 层**，与 `notes` 规格
  「**刻意知识、非某一轮对话的残留**」哲学**一致** ⇒ 规格**纯 ADDED**（不动任何既有条文）。
- **表征 = 每会话一条**：`note_id` 由 `session_id` **确定性派生**（`session-<slug>`）；重复提升**幂等覆盖**、
  **不产生第二条**；复用**既有唯一写路径** `NoteStore.update()`。
- **读面 = 新增只读访问器** `MemoryStore.summary_for(session_id)`（复用私有 `_existing_summary` ⇒
  id 约定**单一真源**；零状态 / 零写入 / 零效应）。

## 为何是「显式触发」而非「自动压实后钩子」

自动触发需要「哪些摘要算重要」的判据，而**现有信号全不可用**（本 change 实证两处，写入 ADR-0142）：

1. **`MemoryEntry.importance` 对摘要条目恒为 `0.0`** —— `_score_importance`（`store.py:326`）只对
   `_episodic_groups`（只收 `kind=="episodic"`）打分，摘要在其后由 `_commit_summary`（`store.py:394`）
   以默认参数创建 ⇒ 「摘要 `importance ≥ 阈值`」是**死判据**（永不触发）。
2. **循环内压实是「全量」而非会话级** —— `default.py:447` 调 `self._memory.compact()`（**无 `session_id`**）
   ⇒ 一次压实为**所有**有 L2 episodic 的会话写摘要 ⇒ 「压实后钩子按 `ctx.session_id` 提升刚写的摘要」**范围错配**。

且自动把会话摘要灌进全局 canonical 层，**直接与 `notes` 规格「刻意知识、非对话残留」的哲学冲突**
（须 MODIFY 哲学条文）。显式动词下「**谁运行 `notes promote`**」这一动作本身就是「有意」的证据 ⇒
**天然符合**该哲学、规格**零既有条文改动**。

## 规格

- `notes` **ADDED Requirement「会话摘要提升（promotion）」**（+6 Scenario）。
- `memory` **MODIFIED Requirement「记忆压实」**：仅在既有 Requirement 内追加**只读访问器** `summary_for`
  条款 + 1 Scenario（**不动**任何摘要 id / trace / 回滚 / 降级口径）。

本项**非** `skip_specs`（新能力、新增公开行为）⇒ 走规格先行、**不写** `.openspec.yaml`。

## 风险与红线

- **⚠️ 密钥红线**：提升产出的 note **自动置常驻** ⇒ 正文**每轮进模型上下文**。因触发**显式**，操作者
  **须在提升前 review 摘要内容**，**绝不**提升含密钥 / 凭据的摘要（承 ADR-0141 红线）。本提案与
  ADR-0142 双重告示。
- **token 有界（P5）**：提升笔记与既有常驻笔记**共享** `_MAX_PINNED_CHARS = 4000` 预算，多篇互相挤占、
  末篇可能截断（承 ADR-0141 局限②）。
- **`notes` 写面不接 `EffectTracker`**（承 ADR-0099 / ADR-0141 取舍）：提升复用同一 `update()` 路径 ⇒
  **一致**；可逆性由 canonical 文件本身（重提升 / 编辑 / 删除 + git）体现。
- **零回归**：`promote_session_summary` 为**新模块纯函数**；`MemoryStore.summary_for` 为**新增只读方法**；
  `notes` 规格既有 4 条 Requirement 的 Scenario **逐字不变**。

## 影响面

新增 `src/core/notes/promote.py`；改动 `src/core/memory/store.py`（+`summary_for`）、
`src/core/memory/protocol.py`（Protocol 同步）、`src/core/notes/__init__.py`（导出）、
`src/core/entry.py`（`notes promote` 子命令 + `_memory_summary`）。
**`src/core/runtime.py` 零改动**（不接 loop、不加钩子、不给上层加触发面）。
测试 `tests/test_memory.py`、`tests/test_notes_promote.py`（新）、`tests/test_notes_loop.py`、
`tests/test_entry.py`、`tests/test_session_isolation.py`；文档 `doc/03-interfaces/{memory,notes}-interface.md`、
`doc/02-modules/{memory,notes}.md`、`doc/04-testing/test-cases.md` §66、`doc/01-architecture/adr.md`
（ADR-0142）、`coding-plan/known-risk.md`（E94 → 已修）。
