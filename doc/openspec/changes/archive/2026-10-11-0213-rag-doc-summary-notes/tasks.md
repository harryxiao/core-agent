# Tasks 0213 — 文档→摘要：`rag ingest --summarize` 落 notes 结论笔记

## 1. 规格（spec-first）

- [x] `specs/rag/spec.md`：**MODIFIED**「文档摄取与分块」（全量替换；narrative 补「可选摘要」/
      「摘要失败不阻断」两 bullets ＋ **ADD** Scenario「摄取可选摘要落结论笔记」；既有 3 Scenarios
      **逐字保留**）
- [x] `specs/notes/spec.md`：**ADDED**「文档摘要笔记（notes.rag）」＋ Scenario ×4
- [x] ADR-0203 +「变更追踪」表行
- [x] 其余 `rag` / `notes` Requirement **逐字保留**

## 2. 测试先行（红）

- [x] 新 `tests/test_rag_summary.py`：
  - `--summarize` ⇒ note 存在且 `source` / `tags` / `pinned` 正确（桩 provider 出网隔离）
  - 重摄取 ⇒ 覆盖不重复（笔记总数不变）
  - `observe_turn` / `promote_session_summary` 后 note **原样**（双守护锚）
  - digest 命中含摘要节选（**非**清单标题通道）
  - 无旗 ⇒ 零 note（零回归锚）
  - `_doc_summary_note` 空 slug 守卫 ⇒ `None`、不写盘
- [x] **反证**：`_rag_ingest` 摘要分支强制关 ⇒ `test_cli_ingest_summarize_writes_note` 红
  （`1 failed, 7 passed`）；把 `_ARCHIVE_SOURCES` 加上 `notes.rag` ⇒
  `test_doc_summary_note_enters_digest_excerpt` 红（`1 failed, 7 passed`）—— 两处均 **md5 复原
  逐字节一致**后复跑 8 passed

## 3. 实现（绿）

- [x] `entry.py`：`_SUMMARY_NOTE_SOURCE = "notes.rag"` + `_doc_summary_note(store, *, doc_id, summary)`
      （**落点由 `notes/rag_summary.py` 订正为入口侧** —— 见 design D4：`notes` 包公开面受 ADR-0148
      结构门禁约束，`entry` 是明列的 rag 例外；零 `notes` 包改动）
- [x] `entry.py`：`_add_rag_parser` 的 `ingest` 加 `--summarize`；`_rag_ingest` 摄取后按旗摘要 +
      落笔记；`_write_doc_summary_note(runtime, *, doc_id, text)` 4 行接缝 + `_DOC_SUMMARY_PROMPT`；
      失败告警只报 `doc_id`
- [x] `_RAG_USAGE` 更新（`ingest ... [--summarize]`）

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
      （**2403 passed**；含 `test_memory_notes_api_excludes_document_corpus_dimension` 绿）
- [x] **反证**：见 §2 末
- [ ] `openspec validate 2026-10-11-0213-rag-doc-summary-notes`
- [ ] 手工归档（MODIFIED 合并 / ADDED 追加；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失）
- [ ] `doc/04-testing/test-cases.md` §126 + 基线 bump；台账 E150（`known-risk.md` §1）+
      §3 ADR-0203 行；`doc/02-modules/notes.md` / `rag.md` 增补；`doc/03-interfaces/notes-interface.md`
- [ ] 单次提交 `feat(rag): 文档→摘要落 notes 结论笔记（change 0213 / ADR-0203 / 台账 E150）`
