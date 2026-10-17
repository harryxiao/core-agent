# Tasks 0252 — 词法检索的 IDF 加权与长度归一

## 1. 规格

- [x] 1.1 `memory` spec delta：MODIFIED「温度分层检索」，补词法 IDF/长度归一与
      未配置 embedder 的启动提示；新增 3 Scenario，既有 Scenario 逐字保留。

## 2. 红测试（先写）

- [x] 2.1 `tests/test_memory_lexical_scoring.py`：
      - 罕见词条目排在常见词条目前（IDF）
      - 同词命中时短文档排在长文档前（长度归一）
      - CJK 二元组检索仍按精确覆盖优先
      - `stats=None` 时 `relevance` / `rank` 与原重叠公式逐字一致
      - `MemoryStore.read` 端到端使用 IDF 排序
      - embedder 抛错时仍用 IDF 词法排序（降级不丢统计）
- [x] 2.2 `tests/test_entry.py`：无 embedding_model ⇒ stderr 有提示；有 ⇒ 无提示。

## 3. 实现

- [x] 3.1 `relevance.py`：`LexicalStats`、`build_lexical_stats`、BM25 `_lexical_sim`、
      `relevance`/`rank` 的 `stats=` 关键字。
- [x] 3.2 `store.py::read`：候选集建 stats 并传入 `rank`。
- [x] 3.3 `entry._build_ui`：无 embedding_model 时输出一次提示。

## 4. 验证

- [x] 4.1 探针：摘 `read` 的 stats 传递 ⇒ 端到端排序用例红；摘 IDF 项 ⇒ 罕见词用例红；
      摘长度归一 ⇒ 短文档用例红；复原 md5 一致。
- [x] 4.2 四门禁：`.venv/bin/ruff check src tests`、`.venv/bin/ruff format --check src tests`、
      `/home/harry/.praisonai/venv/bin/pyright`、`.venv/bin/pytest -q`。
- [x] 4.3 `openspec validate 2026-10-17-0252-memory-lexical-scoring --strict` → 归档。

## 5. 文档与收口

- [x] 5.1 ADR-0242；`coding-plan/known-risk.md` E188 + §3 ADR-0242 行。
- [x] 5.2 `doc/04-testing/test-cases.md` §164；`doc/02-modules/memory.md` §3.2 更新；
      `doc/03-interfaces/memory-interface.md` §3 更新。
- [x] 5.3 单次提交 `feat(memory): ... change 0252 / ADR-0242 / 台账 E188`；更新记忆。
