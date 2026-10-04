# Tasks: 记忆检索多因子化

## 1. 规格先行

- [x] 1.1 `specs/memory/spec.md` delta：MODIFIED「温度分层检索」（多因子重排 / 语义相似经
      embedder+缓存 / 条目 kind·importance 场景）
- [x] 1.2 `openspec validate 0039-memory-multifactor-recall` 全绿

## 2. 契约与接口文档

- [x] 2.1 `03-interfaces/memory-interface.md`：`MemoryEntry` 增 `importance`/`kind`；§3
      相关性打分公式更新为多因子；补 embedder 批量契约 + 缓存语义

## 3. 测试先行（先红）

- [x] 3.1 `tests/test_memory.py`：`MemoryEntry` 默认值（`importance=0.0`、`kind="episodic"`）
      且不影响旧 JSONL 记录加载
- [x] 3.2 `tests/test_memory.py`：多因子排序——同等相似度下高 `importance` / 高
      `reuse_count` 条目排前；`read` 命中后 `reuse_count` +1
- [x] 3.3 `tests/test_memory.py`：注入 fake embedder——`read` 中 query **只向量化一次**、
      未变条目向量**复用缓存**（用计数 embedder 断言调用次数）
- [x] 3.4 `tests/test_memory.py`：embedder 抛异常时降级词法，不抛
- [x] 3.5 `tests/test_phase13.py`：`build_runtime(embedder=fake)` 透传至 `memory._embedder`；
      默认 `None`

## 4. 实现

- [x] 4.1 `memory/protocol.py`：`MemoryEntry` 增 `importance`/`kind`（置于 `session_id` 后）
- [x] 4.2 `memory/embedding.py`（新）：`batch_embed(single) -> batch`
- [x] 4.3 `memory/relevance.py`：`relevance` 收敛为 `sim·w + layer·w`；新增 `recency_decay`
- [x] 4.4 `memory/store.py`：`_rank(e, query, embedder, cache)` 多因子；`read` 单次 query
      向量化 + `(id, hash)` 向量缓存；命中 `reuse_count += 1`
- [x] 4.5 `runtime.py`：`build_runtime` 增 `embedder=None` DI 参数并透传给 `MemoryStore`

## 5. 门禁

- [x] 5.1 ruff check / format 全绿
- [x] 5.2 pyright（src）0 error
- [x] 5.3 `.venv/bin/pytest -q` 全绿
- [x] 5.4 `openspec validate --all` 全绿 → 归档（delta 合并进 specs/ + 同步
      `04-testing/test-cases.md` 追踪号）
