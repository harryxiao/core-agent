# 任务 — 0290 记忆语义检索异步安全化 ＋ 批量相似

## 1. 规格

- [x] 1.1 `specs/llm-provider/spec.md`：MODIFIED「异步调用接口」（循环内工作线程桥接、
      阻塞语义、不留未等待协程），改「同步薄壳等价」、新增「运行中事件循环内的同步薄壳」。
- [x] 1.2 `specs/memory/spec.md`：MODIFIED「温度分层检索」（批量相似、空集不触网、
      整次降级不混合），改两个 Scenario、新增两个 Scenario。
- [x] 1.3 `openspec validate 2026-10-18-0290-memory-semantic-async` 与 `validate --all` 全绿。

## 2. 代码（测试先行）

- [x] 2.1 `tests/test_llm_provider.py`：循环内三个薄壳可用、工作线程执行、
      `LLMError` 透传且无 `RuntimeWarning`。
- [x] 2.2 `tests/test_rag.py`：`embed_many` 单次调用、错误映射、空输入、循环内可用。
- [x] 2.3 `tests/test_memory_batch_similarity.py`：余弦映射、分块与 query 一次、
      空集不触网、异常/数量/维度 ⇒ `None`、默认批上界、循环内端到端。
- [x] 2.4 `tests/test_memory_lexical_scoring.py`：`sim` 预计算（含 `0.0`）不调用 embedder。
- [x] 2.5 `tests/test_memory.py`：130 候选 64/64/3、第二块失败整次词法、空 store 不触网。
- [x] 2.6 `tests/test_phase13.py`：组合根注入断言改为一次 provider 调用。
- [x] 2.7 `src/core/llm_provider/provider.py`：`_run_sync` + 三个薄壳。
- [x] 2.8 `src/core/rag/embedder.py`：`LLMEmbedder.embed_many`。
- [x] 2.9 `src/core/memory/relevance.py`：`batch_similarities` + `sim` 关键字。
- [x] 2.10 `src/core/memory/store.py`：`read` 批量相似 + 整次降级。
- [x] 2.11 `src/core/runtime.py`：注入 `LLMEmbedder(...).embed_many`。

## 3. 文档

- [x] 3.1 `doc/01-architecture/adr.md`：ADR-0280。
- [x] 3.2 `coding-plan/known-risk.md`：E226 行 + ADR-0280 局限索引。
- [x] 3.3 `doc/04-testing/test-cases.md`：§203；更新 :1297 旧注记。
- [x] 3.4 `doc/03-interfaces/llm-provider-interface.md` / `doc/02-modules/llm-provider.md`。
- [x] 3.5 `doc/03-interfaces/memory-interface.md` / `doc/02-modules/memory.md`。
- [x] 3.6 `doc/03-interfaces/rag-interface.md`：`LLMEmbedder.embed_many`。

## 4. 门禁

- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`
- [x] 4.4 `.venv/bin/pytest -q`（3221 → 3241）
- [x] 4.5 反证 3/3（cp 到 /tmp，禁 `git checkout`；复原后 md5sum 一致）。
- [x] 4.6 端到端：真实 embedding 端点在 `asyncio.run` 内检索，无告警且语义排序生效。
- [x] 4.7 `openspec archive -y 2026-10-18-0290-memory-semantic-async` 后再跑 `validate --all`。
- [x] 4.8 仅暂存本 change 路径并提交。
