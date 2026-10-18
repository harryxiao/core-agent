# 0290 — 记忆语义检索异步安全化 ＋ 批量相似

## Why

2026-10-18 的真实 `task` 冒烟在运行中打印：

```
RuntimeWarning: coroutine 'StdlibLLMProvider.aembedding' was never awaited
```

根因链（逐环可复现）：`MemoryStore.read` 在事件循环线程上同步执行 → 逐候选调用
`relevance._similarity` → `batch_embed` 串行适配 → `LLMEmbedder.embed` →
`LLMProvider.embedding` 的 `asyncio.run` → 循环嵌套 `RuntimeError` → `_memo_embedder`
置**粘性** `_embed_failed=True` ⇒ 本进程后续所有检索都只剩词法。
`llm.embedding_required` 抓不到该问题（规格明确它只做配置期阻断、不探测可达性）。

同一路径还有第二个规模问题：逐候选调用 embedder ⇒ N 条候选 N 次远端往返；
即使桥接修好，10k 候选仍是 10k 次调用。

## What Changes

- **同步薄壳循环安全**（`LLMProvider`）：`completion` / `stream` / `embedding` 在无运行
  循环时保持 `asyncio.run`；在运行中事件循环内改在一次性工作线程的新循环执行同一异步
  实现并等待。传入协程工厂，桥接失败不留下未等待协程。两种上下文均为阻塞语义。
- **批量向量化契约**：`LLMEmbedder.embed_many(texts)` 一次 provider 调用收齐一个批次；
  组合根 memory 通路由 `batch_embed(LLMEmbedder.embed)` 改为 `LLMEmbedder.embed_many`。
  `batch_embed` 保留为注入单文本 callable 的兼容适配器。
- **检索前批量相似**：`relevance.batch_similarities` 按 64 条一批（query 恒在第一批、
  至多一次），返回 `id → 余弦`；`MemoryStore.read` 排序前调用，`rank` 接受预计算 `sim`。
  空候选集不调用 embedder；任一批异常/数量或维度不符 ⇒ 本次检索**整体**走 BM25，
  不出现余弦/词法混合排序。
- **行为边界不变**：缺省词法路径、`embedding_required` 配置期语义、粘性失败后的词法
  降级均逐字保留。新局限如实登记：同步桥仍阻塞事件循环、一次性线程不复用连接、
  4096 条 FIFO 向量缓存仍会抖动；真正的延迟修复（语义 top-K 预筛）不在本 change。

## Non-goals

- 不把 `MemoryStore.read` / `ContextAssembler.build` / planner prompt 异步化。
- 不做语义 top-K 预筛或 rerank（另立 change）。
- 不调大 `_VEC_CACHE_MAX`、不改 FIFO/LRU、不改粘性失败策略、不加运行时探测/重试。
- 不把 `embed_many` 加入 `Embedder` ABC，不删除 `batch_embed`，不做增量跨线程 `stream`。
- 不新增配置项、不新增 CLI 子命令、不引入第三方 LLM SDK。

## Impact

- 代码：`src/core/llm_provider/provider.py`、`src/core/rag/embedder.py`、
  `src/core/memory/relevance.py`、`src/core/memory/store.py`、`src/core/runtime.py`。
- 规格：`llm-provider`（异步调用接口）、`memory`（温度分层检索）两个 MODIFIED delta。
- 测试：新增 20 个用例（provider 3 / rag 4 / 批量相似 8 / 词法预计算 2 / memory 3），
  修改 `test_phase13` 的注入断言；全量 3221 → **3241**。
- 文档：ADR-0280、台账 E226、test-cases §203、llm-provider / memory 接口与模块文档。
- 缺省行为：未注入 embedder 的部署逐字不变；注入 embedder 时调用次数变为按批，
  排序尺度在成功/失败两种情况下都一致（不再混合）。
