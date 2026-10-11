# Tasks 0210 — rag 文档进信息地图

## 1. 规格（spec-first）

- [x] `specs/context/spec.md`：**MODIFIED**「信息地图」（全量替换；narrative 补文档来源 / `index` vs
      `register` / 块序号拼回 / 总量上限 / 逐文档降级 / 旗关逐字不变 ＋ **ADD** Scenario ×3；
      既有 3 Scenario **逐字保留**）
- [x] `specs/rag/spec.md`：**MODIFIED**「本地向量库存储」（全量替换；narrative 补两个 **fail-soft
      读侧访问器** ＋ **ADD** Scenario「块文本按序号拼回原文」；既有 3 Scenario **逐字保留**）
- [x] ADR-0200 +「变更追踪」表行
- [x] 其余 `context` / `rag` Requirement **逐字保留**

## 2. 测试先行（红）

- [x] `tests/test_rag_wiring.py` 增补：>10 块数字序往返 == 原文（字典序会红）；组合根旗开 ⇒
      `pointers` 含 rag 文档目录 / 旗关 ⇒ 与改前**逐字同**（零回归锚）；20 文档 ⇒ 只 16 进地图
- [x] **反证**：摘文档数上限 ⇒ 20 文档用例红；摘旗 ⇒ 旗开用例红

## 3. 实现（绿）

- [x] `rag/vector_store.py`：`VectorStore` 补 `document_ids()` / `chunk_texts(doc_id)`（**非抽象**、
      缺省返 `[]`）；`SqliteVectorStore` / `InMemoryVectorStore` 实现（块按**数字后缀序**）
- [x] `configuration/manager.py`：ConfigSpec `context.rag_info_map`（bool 缺省 False）＋ 访问器
      `rag_info_map()`（`context` 非结构化段 ⇒ 集合外归一为关）
- [x] `runtime.py`：`rag_store` 局部引用 ＋ `_index_rag_docs(info_map, store)` 模块级 helper
      （上限 `_RAG_INFO_MAP_MAX_DOCS=16`、跳过 `core-profile`、`index` 非 `register`、逐文档降级）

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] **反证**：见 §2 末
- [x] `openspec validate 2026-10-11-0210-rag-info-map`
- [x] 手工归档（MODIFIED 合并，Scenario 追加；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失）
- [x] `doc/04-testing/test-cases.md` §123 + 基线 bump；台账 E147（`known-risk.md` §1）+
      §3 ADR-0200 行；`doc/02-modules/rag.md` / `context.md` 增补
- [x] 单次提交 `feat(context): rag 文档进信息地图（change 0210 / ADR-0200 / 台账 E147）`
