# 任务：三面边界**另一侧**门禁（change 0189 / ADR-0148 附 / 台账 E126）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> 本 change **规格中性**（`.openspec.yaml` `skip_specs: true`）⇒「测试先行」体现为**结构门禁**：
> 现状应**绿**（既有边界即满足）；**红态**由人工植入越界签名确认（沿 change `0156` tasks 2.2 先例）。
> 状态：**已归档**（2026-10-10；四门禁全绿，`openspec validate 2026-10-10-0189-three-face-boundary-guard`
> ⇒ valid；全量 `.venv/bin/pytest -q` 基线 **2206** ⇒ **2208**）。

## 1. 定位与规格判断（先行）

- [x] 1.1 一手核实**守护不对称**：`test_rag_not_imported_by_reference_chain` 的链
      `{loop, context, memory, notes}` **含** memory / notes，但只断 `import core.rag`（**只护 rag 一侧**）
- [x] 1.2 一手核实**既有守护**：`test_session_isolation.py::test_notes_api_has_no_session_dimension`
      已钉会话维度侧 ⇒ 本 change **不重复**（改钉**语料维度**侧）
- [x] 1.3 判定**规格中性**（无 SHALL 变更）⇒ `skip_specs: true`；门径钉死：越界须**先改 ADR-0148**、
      再开规格变更（决策③）

## 2. 测试先行（门禁）

- [x] 2.1 `tests/test_architecture.py`：抽常量 `_REFERENCE_CHAIN`（既有 rag 守护改用之，**断言逐字不变**）
      ＋ 新常量 `_CORPUS_FREE_FACES` / `_CORPUS_DIMENSION_TOKENS`
- [x] 2.2 新增守护 ① 链成员：`_CORPUS_FREE_FACES ⊆ _REFERENCE_CHAIN`
      （`test_rag_guard_chain_covers_corpus_free_faces`）
- [x] 2.3 新增守护 ② 语料维度：`ast` 走查两面**公开面**（名 ＋ 形参）词元命中即红，并断言走查**非空**
      （`test_memory_notes_api_excludes_document_corpus_dimension`）
- [x] 2.4 红态确认：临时植入 `src/core/notes/store.py` 公开函数
      `ingest_document(path, chunks)` ⇒ 门禁**变红且指名** `notes/store.py:361 ingest_document ->
      ['document','ingest']` / `chunks -> ['chunks']`；`git checkout` 撤销 ⇒ 回绿（`src/` 零改动）
- [x] 2.5 误报边界：词表**刻意不含** `vector` / `embed`（memory 语义记忆面**合法**使用嵌入，
      见 design.md D3）；切分而非子串比对（`fragment` 不命中 `rag`）

## 3. 文档与 ADR

- [x] 3.1 `doc/01-architecture/adr.md`：**ADR-0148 附记**（局限② 收口 + ②③ 收窄 + 词表口径 + 不重复既有守护）
- [x] 3.2 `doc/04-testing/test-cases.md`：新增 `## 102.` 节（TC-BOUNDARY-01/02/03 ＋ TC-RAG-14 回归锚 ＋
      红态证据 ＋ 基线 bump 2206 ⇒ 2208）

## 4. 台账

- [x] 4.1 `coding-plan/known-risk.md` §1：新立 **E126**（已闭）
- [x] 4.2 `coding-plan/known-risk.md` §3：ADR-0148 行局限②③ 改注（收窄后余项）

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ 380 files already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ **2208 passed**（基线 **2206**，**+2**）
- [x] 5.5 `openspec validate 2026-10-10-0189-three-face-boundary-guard` ⇒ **valid**（`skip_specs` ⇒ 无 delta）
- [x] 5.6 手工归档：`shutil.move` 至 `archive/2026-10-10-0189-three-face-boundary-guard/`

## 6. 记忆与提交

- [x] 6.1 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`；批次 `Phase 35` 全闭）
- [x] 6.2 单次提交：`test(architecture): 三面边界另一侧门禁 —— memory / notes 不得兼做知识文档检索
      （change 0189 / ADR-0148 附 / 台账 E126）`
