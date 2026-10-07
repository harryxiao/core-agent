# 笔记写入来源守护（notes write provenance guard）· change 0151 · 账本 E95

## 为什么

`notes` 是**刻意文档化的权威真相层**（canonical Markdown，覆盖式「最新即权威」）。但当前**两条自动 /
半自动写路径**都**无条件覆写**目标主题，**不看该主题由谁产生**：

1. **逐轮写回 `observe_turn`**（`src/core/notes/store.py`）——每成功轮把「## 解决过程 + 步骤列表」
   覆盖式写回 `slug_topic(task)` 主题。覆写时**只保留 `tags` 与 `pinned`**，`content` 与 `title`
   **全量替换**。⇒ 人工撰写 / promotion 产出 / 其他来源的笔记，**只要 `note_id` 撞上任务 slug**，
   正文就被**静默**替换为步骤列表；若该笔记 `pinned`，**标记保留、内容被换** ⇒ 此后每轮「任务级
   硬约束」块注入的**就是步骤列表**（E93 常驻语义被静默污染）。
2. **提升 `promote_session_summary`**（`src/core/notes/promote.py`）——把会话摘要写回派生
   `session-<slug>` 主题，**无条件覆写、强制 `pinned=True`、改写 `source`**；撞上同 id 的人工笔记
   时**无守护、无提示**。

这是**一条缺失的写入安全契约**，而非理论风险（`observe_turn` 那处是**真缺陷**）。

## 改什么

给两条写路径加**来源守护（provenance guard）**：**一条主题只应由产生它的那条路径覆写**。

- **`observe_turn`（C1）**：覆写前读既有笔记；若其 `source != "notes.turn"` ⇒ **不改写该主题**，
  本轮沉淀改写到首个**不冲突**的派生主题 `<topic>-<n>`（`n` 取 2 起首个「不存在或归属
  `notes.turn`」者）。⇒ **绝不**覆写外来源正文，**也不丢**本轮沉淀。既有「同来源覆盖式写回」
  行为**逐字不变**（含保留 `tags` / `pinned`）。
- **`promote_session_summary`（C2）**：派生 id 撞上 `source != "notes.promote"` 的既有笔记、且调用方
  **未**显式给 `--as` ⇒ **不写盘**、返回 `None`、CLI **非零退出**（复用既有「空 slug ⇒ None + 非零」
  口径，**不新增错误码**）。给了 `--as` ⇒ 视为**显式授权**，照常覆写。

### 设计原则（与架构同向）

- **不删除任何笔记**（承 memory 层「降权/归档而非删除」取向；notes 无自动清理是**设计意图**）。
- **来源决定写权限** —— 与 `observe_turn` 既有「保留 tags/pinned」的意图是同一件事的**完成**，
  不是新增语义；「最新即权威」是 ADR-0099 的**有意契约**，本 change **不推翻**，只约束**跨来源**覆写。
- **误覆写要可见**：撞车不静默（CLI 报错非零；逐轮写回改道派生主题）。

## 规格

- `notes` **MODIFIED Requirement「Consult → Build → Update 循环纪律」**：追加**来源守护**条款
  （`observe_turn` 撞外来源 ⇒ 改道派生主题）+ 1 Scenario。
- `notes` **MODIFIED Requirement「会话摘要提升（promotion）」**：追加**撞车拒绝**条款
  （撞非 promotion 来源且未给 `--as` ⇒ 不写盘 + 非零退出）+ 1 Scenario。
- 其余 Requirement 的 Scenario **逐字不变**（零回归）。

本项**非** `skip_specs`（行为变更、可见契约）⇒ 走规格先行、**不写** `.openspec.yaml`。

## 非目标（明确不做）

- **不做** notes 版本控制 / CAS / 三路合并 / 归档区（ADR-0099 决策② 维持：MVP 不切三分区）。
- **不做** 最小可回溯（`notes/.history/`）—— provenance 守护已堵住误覆写主因；引入新目录/生命周期面
  留待另立账。
- **不推翻**「覆盖式（最新即权威）」契约 —— 只约束**跨来源**覆写。
- **不改** `rag`、**不引入**本地语义模型（承 `rag-offline-embedder-decision`）。
- **不新增** notes 错误码；**不接** `EffectTracker`（承 ADR-0099）。

## 风险与红线

- **密钥红线**：笔记正文可能每轮进模型上下文（常驻），故**绝不**在笔记中落密钥 / 凭据；本 change
  只改**谁的正文被谁覆写**，不引入任何新写入内容面。
- **token 有界（P5）**：本 change **不改**常驻预算（`_MAX_PINNED_CHARS = 4000`）；pinned 预算的
  **判据与可见性**（谁在场、超限留痕）**另立账 G1**（承 ADR-0141 局限②）。
- **零回归**：既有 `notes` 用例（`tests/test_notes.py` / `test_notes_loop.py` / `test_notes_promote.py` /
  `test_entry.py`）逐字不动、全绿。

## 影响面

改动 `src/core/notes/store.py`（`observe_turn` 来源守护 + 派生主题辅助 + 来源常量）、
`src/core/notes/promote.py`（撞车拒绝）、`src/core/entry.py`（`_notes_promote` 撞车报错文案）。
测试 `tests/test_notes.py`、`tests/test_notes_promote.py`、`tests/test_entry.py`（新增用例）；
文档 `doc/02-modules/notes.md`、`doc/03-interfaces/notes-interface.md`、
`doc/04-testing/test-cases.md`（新 `## 67.` TC-WRITESAFE）、`doc/01-architecture/adr.md`（ADR-0143）、
`coding-plan/known-risk.md`（E95 立账）。
