# Design 0213 — 文档→摘要：`rag ingest --summarize` 落 notes 结论笔记

## D1 落点 = notes 结论层（用户裁决）

「原始文档 → 摘要」有两条可选落点：**rag 库**（把摘要当又一块 chunk 存进向量库）或 **notes**
（canonical 结论层）。裁决落 **notes**：

- rag 是**检索**面（chunk 相似度召回），把摘要塞回 chunk 面会**污染检索语料**（摘要与原文重复入场）；
- notes 是**真相/结论**面，`digest` 会按 Consult 命中注入推理上下文 —— 正是「这份文档讲了什么」
  该在的位置；
- 守 **RAG 三面边界**（ADR-0097⑥ / ADR-0148，`tests/test_architecture.py:326-347` 守护）：
  `rag` 包**不感知** notes，桥搭在**入口侧**（`entry._rag_ingest`）。

## D2 显式旗即 opt-in，无配置键

`--summarize` 是**一次性的显式意图**（「这次摄取顺便总结」）—— 无需 `features.*` / `rag.*` 配置键，
也**无环境行为**（不带旗 ⇒ 逐字不变）。这与「缺省关的新行为」纪律**不冲突**：此处不是「隐藏的
缺省行为」，而是「显式的每命令参数」。摘要本身**不落新的运行时态**（除 canonical 笔记）。

## D3 摘要调用 = 入口侧复刻 `_llm_text` 4 行接缝

组合根的 `_llm_text`（`runtime.py:536-541`）是**闭包**、不可外部取用。入口侧 `_rag_ingest`
**已有** `runtime`（装配于 `_rag`）⇒ 直接 `runtime.llm.completion(LLMRequest(...,
model=runtime.app.llm.model))` 复刻同一 4 行形状。**不复用** `memory/summarize.py`（那是**会话压实**
形状：多轮 → 摘要，输入是 `MemoryEntry` 列表）；此处是**单文档全文 → 摘要**，形状不同。

## D4 入口侧 `entry._doc_summary_note` 镜像 `promote.py`

**落点订正（实施期）**：初版拟新 `src/core/notes/rag_summary.py::write_doc_summary`，被本仓
**ADR-0148 三面边界**的结构门禁 `tests/test_architecture.py::test_memory_notes_api_excludes_document_corpus_dimension`
判红（`_public_api_identifiers` 抽出 `write_doc_summary` / `doc_id` ⇒ 命中 `doc` 语料词元）。
该门禁是 change `0189`／E126 立的**不变量**，其 docstring 明写：「先改 ADR、再开规格变更，而非
顺手补签名」—— 本 change 的规格/裁决**不**含「放开 notes 包承载文档语料」，故**不退门禁**、
改**落点**：桥移到 `entry`（`test_rag_not_imported_by_reference_chain` 明列的 rag 例外），
调用**公开** `NoteStore.update`（`notes` 包**零改动**）。行为与初版**逐字相同**。

| 维度 | promotion | 文档摘要（本 change） |
|---|---|---|
| 输入 | `MemoryEntry`（会话摘要） | `doc_id` + `summary: str` |
| `note_id` | `session-<slug(session_id)>` | `doc-<slug(doc_id)>` |
| `source` | `notes.promote` | `notes.rag`（`entry._SUMMARY_NOTE_SOURCE`） |
| `pinned` | 缺省 `True`（CLI）/ `False`（半自动） | **恒 `False`**（不占常驻预算） |
| 写路径 | `store.update`（`notes` 包内） | `store.update`（**同一**唯一写路径） |
| 空 slug 守卫 | 返回 `None` | 返回 `None`（同一口径） |
| 落点 | `notes/promote.py` | `entry.py`（守 ADR-0148 公开面） |

**不同点**：promote 有「来源守护」（撞非 `notes.promote` 的既有笔记 ⇒ 不写，需显式 `as_note_id`）；
本函数**不需要** —— `note_id` 前缀 `doc-` 与 `session-` 天然不同命名空间，且 `_doc_summary_note`
的语义**就是**「覆盖这篇文档的摘要」，撞名即刷新。

## D5 「双守护」是**免费获得**、非新机制

`notes.rag` 不进任何覆写路径的目标：

- `observe_turn`（`store.py:267-307`）：只覆写 `source == notes.turn` 的笔记；撞上 `notes.rag`
  笔记 ⇒ 走 `<topic>-<n>` 回落（`store.py:294` 的来源守护）；
- `promote_session_summary`（`promote.py:57-58`）：撞上非 `notes.promote` 的既有笔记且未显式
  `as_note_id` ⇒ 返回 `None`，**不写盘**。

⇒ 本 change **零改动**这两条路径，摘要笔记天然受保护（`test_rag_summary.py` 以锚点证明）。

## D6 进 digest 命中节选（**刻意不**入 `_ARCHIVE_SOURCES`）

`_ARCHIVE_SOURCES = frozenset({PROMOTE_SOURCE})`（`store.py:54`）—— 其存在理由是「提升产物正文
源自 memory 会话摘要、已由 loop『历史摘要』块每轮注入，避免**重复**」。文档摘要**无**此重复来源
⇒ **不入**归档来源 ⇒ 进 digest 的「命中的笔记」**节选**块。这是**目的**（结论层要在上下文可见），
**非**疏漏 —— 本 change 不动 `_ARCHIVE_SOURCES`。

## D7 失败不阻断摄取

摘要（模型调用 / 落盘）失败 **不**回退已完成的摄取、**不**使命令非零退出（摄取已是既成事实）；
失败告警落 **stderr**、**只报 `doc_id`**（**绝不回显正文 / 摘要正文 / 任何密钥**）。

## D8 已知局限（登记 ADR-0203「局限」）

1. **摘要质量无门** —— 一次性 LLM 调用，无 JEV 质量门（如需另立 change）；
2. **大文档全文直喂** —— 无分段 / 递归摘要（超出模型窗口由调用方自理）；
3. **重摄取才刷新** —— 摘要与文档内容绑定于摄取时刻，源文档改了但未重摄取 ⇒ 摘要是旧的
   （与 rag 索引同生命周期：改内容需重摄取）；
4. **CLI 专属入口** —— 无 Agent 工具 / 无 API 触发摘要（摄取本就是 CLI 一次性动作）。
