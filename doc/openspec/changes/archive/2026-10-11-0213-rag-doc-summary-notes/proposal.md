# Proposal 0213 — 文档→摘要：`rag ingest --summarize` 落 notes 结论笔记

## 为什么

六能力走查确认：「**原始文档 → 可持久化摘要**」**没有入口**：

- `rag ingest`（`entry.py:1628-1639`）只做「分块 → embedding → 落索引」，`rag ask`（`:1656-1659`）
  是**一次性**问答、不落盘 —— 系统里的「总结」全是**会话结晶**（记忆压实 / 提升），
  **没有**「把一份知识文档本身的结论沉淀成可复用真相」的路径。
- 目录层（`0210` 的 InfoMap）解决「有哪些文档」，检索层（rag）解决「哪段相关」，
  但**「这份文档讲了什么」**这一结论层缺失 —— 每次都要重新 `ask`（烧 token、无沉淀）。

## 做什么

### 1. `rag ingest <path> --doc-id ID --summarize`

- `_add_rag_parser` 的 `ingest` 子命令加 `--summarize` 旗（`store_true`）。
- 摄取**成功**后，入口侧把**全文**交给一次 LLM 调用产出摘要（复刻组合根 `_llm_text` 4 行接缝；
  `runtime.llm` / `runtime.app.llm.model` 在手），再经 `_doc_summary_note` 落 canonical 笔记。
- **显式旗即 opt-in**：无 `--summarize` ⇒ 行为**逐字不变**（零配置键、零环境行为）。

### 2. 入口侧 `entry.py::_doc_summary_note`（**不落 notes 包**）

- 形状镜像 `promote.py`：`_doc_summary_note(store, *, doc_id, summary) -> NoteEntry | None`。
- `note_id = f"doc-{slug_topic(doc_id)}"`；`source="notes.rag"`；`tags=["rag", f"doc:{doc_id}", "summary"]`；
  **不 pinned**（不占常驻预算 —— 结论层只经 Consult 命中面 / digest 注入）。
- **幂等覆盖**（`store.update` 是**唯一**写路径）：重摄取 ⇒ 刷新同一 note、不增长。
- **落点为何在入口侧**（**实施期订正**，见 design D4）：`notes` 包的**公开面**不得承载「外部文档
  语料」维度（`doc` / `rag` …）—— ADR-0148 三面边界由 `tests/test_architecture.py::test_memory_notes_api_excludes_document_corpus_dimension`
  以 AST 结构门禁钉死（先版 `notes/rag_summary.py::write_doc_summary` 被该门禁判红：`write_doc_summary -> ['doc']`）。
  `entry` 是 `test_rag_not_imported_by_reference_chain` 明列的**两个 rag 例外**之一 ⇒ 桥搭在此处，
  直接复用 `NoteStore.update`（**零** `notes` 包改动）。

### 3. 双守护「免费」获得 + 进 Consult 命中面

- `observe_turn` 只覆写 `notes.turn`（`store.py:294`）、`promote_session_summary` 只覆写
  `notes.promote`（`promote.py:57`）⇒ `notes.rag` 两路**都不碰**（另加来源守护兜底撞名）。
- `_ARCHIVE_SOURCES` 只含 `promote`（`store.py:54`）⇒ 文档摘要**进 digest 命中节选面**
  （正是目的：结论层要在推理上下文里可见）。

## 不做（边界）

- **不给摘要加质量门**（一次性 LLM 调用，无 JEV 门；如需另立 change）。
- **不做分段 / 递归摘要**（大文档全文直喂；上限由模型窗口兜）。
- **不让 rag 包感知 notes**（落笔记在**入口侧** —— 守 RAG 三面边界 ADR-0097⑥ / ADR-0148）。
- **不改 `_ARCHIVE_SOURCES`**（rag 摘要**不**属归档来源）。
- **不改 `notes` 包**（复用公开 `NoteStore.update`；`_doc_summary_note` 是入口侧私有函数）。
