# 提案 — rag 主链路接线（change 0104）

## Why

`coding-plan/phase-22.md` §3 缺陷 2（P1）：`rag` 模块除 `LLMEmbedder`（供 memory 语义 embedding）外，
**主链路 7 个类全部零生产调用、零 CLI 入口** —— `IngestionPipeline` / `Retriever` / `RagGenerator` /
`InMemoryVectorStore` / `Chunk` / `SearchHit` / `Document`。契约（`doc/openspec/specs/rag/spec.md`）
明文承诺「检索增强生成（摄取→向量化→检索→生成）」，但三端都没接，是「写了没接」的断层。

同审还发现两处**文档失真**（本次一并订正）：

1. 规格与模块文档称向量库「与 Core-Agent **既有 SQLite 生态**统一」—— 全仓 `src/` **无任何 sqlite 使用**
   （`grep -rn "import sqlite3" src/core` 为空），该前提**不成立**。
2. 规格称「默认实现为 **sqlite-vec**」—— 三方 C 扩展，离线环境不可得、亦未在本仓声明依赖。

## What Changes

按 **phase-22 §3.2 (a) 接线**（用户裁决），补：

- **落盘向量库 `SqliteVectorStore`**：stdlib `sqlite3`（**零三方依赖**、嵌入式、零服务），索引落
  `$CORE_STATE_DIR/rag-index.db`；向量以 BLOB 存储、相似度在进程内计算；索引记录**向量维度**，
  写入 / 检索维度与索引不一致时以结构化错误拒绝（须重建索引）——否则换 embedding 后端后
  `zip(strict=False)` 会**静默**截断成错误相似度。
- **`RagService` 门面**：把 `IngestionPipeline → VectorStore → Retriever → RagGenerator` 串成单一入口
  （`ingest` / `refresh` / `search` / `ask`），组合根 `build_runtime` 装配并挂到 `runtime.rag`。
- **CLI 一次性子命令**：`rag ingest <path> [--doc-id ID]` / `rag search <query> [--top-k N]` /
  `rag ask <query> [--top-k N]`（第三者为检索 + 生成融合；前两者不依赖 LLM）。
- **embedding 选择**：配了 `llm.embedding_model` ⇒ `LLMEmbedder`（语义优先，沿用 memory 既有决策）；
  未配 ⇒ `HashEmbedder` 离线降级基线（命令可用性优先，打印降级提示）。
- **规格订正**：`rag/spec.md`「本地向量库存储」订正**默认实现口径**（stdlib sqlite3 嵌入式，
  sqlite-vec 可得时经同一抽象替换）+ 维度一致性；`cli-ops/spec.md`「运维命令集」纳入三个一次性子命令。

## Non-goals

- **不把 RAG 注入 loop 推理链**（phase-22 未要求；跑 `rag ask` 即拿到「检索 + 生成」闭环）。
- **不引入三方依赖**（不装 `sqlite-vec` / `sentence-transformers` / 向量库 SDK）。
- **不改 memory 的 embedding 通路**（`batch_embed(LLMEmbedder(...))` 一字不动）。
- **不做索引分片 / ANN 近似检索 / 增量 rebuild 的并发隔离**（规模未到，保持暴力余弦）。
- **不复用 `InMemoryVectorStore` 当生产实现**（进程退出即丢 ⇒ `ingest` 与 `search` 跨进程不可用）。

## 影响面

| 面 | 变更 |
|---|---|
| `src/core/rag/vector_store.py` | 新增 `SqliteVectorStore`（stdlib `sqlite3`，BLOB 向量、维度校验） |
| `src/core/rag/service.py`（新） | `RagService` 门面（摄取 / 检索 / 生成融合的单一入口） |
| `src/core/rag/__init__.py` | 导出 `RagService` / `SqliteVectorStore` |
| `src/core/runtime.py` | 装配 rag 栈并挂 `runtime.rag`（embedder 选择 + 落盘索引路径） |
| `src/core/entry.py` | `rag` 命令族（`ingest` / `search` / `ask`）+ `_HANDLERS` 注册 |
| 规格 | MODIFIED「本地向量库存储」（rag） / 「运维命令集」（cli-ops） |
| 文档 | `rag-interface.md` §1 / §6、`02-modules/rag.md`（订正失真）、ADR-0097、`test-cases.md` |
