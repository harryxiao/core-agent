# 设计 — rag 主链路接线（change 0104）

## 1. 决策：落盘用 stdlib `sqlite3`，而不是三方 `sqlite-vec` / 也不是 JSON 文件

**问题**：主链路要接线 ⇒ 索引必须**跨进程存活**（`rag ingest` 与 `rag search` 是两次进程调用）。
现有实现只有 `InMemoryVectorStore`（进程退出即丢）。

| 方案 | 评价 |
|---|---|
| (i) 三方 `sqlite-vec` 扩展（规格原文「默认实现」） | **离线不可得**、需声明新依赖；违反「尽量不依赖三方库」 |
| (ii) 三方向量库（Chroma / FAISS） | 同上，且引入 daemon/SDK 面 |
| (iii) JSON 文件 + 原子写（照 `skills.json` / `mcp-endpoints.json` 先例） | 零依赖、全仓一致；但向量以浮点数组整文件重写，**每次 put 重写全量**，随规模退化 |
| **(iv) stdlib `sqlite3`（采纳）** | **零三方依赖**（stdlib）、嵌入式、零服务 —— 与规格「嵌入式零服务、与 SQLite 统一」的**意图**一致；行级写入 / 按文档删除（`DELETE WHERE doc_id`）天然支持**增量重建**，无需重写全量 |

**采纳 (iv)**：`SqliteVectorStore(path)`，向量以 BLOB（`array("d")`）存储，相似度在进程内暴力余弦计算
（规模未到 ANN 门槛）。规格**订正默认实现口径**为 stdlib `sqlite3`（`sqlite-vec` 可得时经同一抽象替换）。

**顺带订正文档失真**：规格与 `02-modules/rag.md` 称「与 Core-Agent **既有 SQLite 生态**统一」——
全仓 `src/` **无任何 sqlite 使用**，该前提不成立，一并订正。

## 2. 决策：索引记录**向量维度**，不一致即结构化拒绝（不静默截断）

**问题**：`_cosine_similarity` 用 `zip(a, b, strict=False)` ⇒ 维度不同的两个向量**静默按短边截断**
比较，产出无意义的相似度。而维度随 embedding 后端变化：缺省 `HashEmbedder` 是 **128** 维，
配了 `llm.embedding_model` 走 `LLMEmbedder` 则是模型维度（如 1024）。同一索引文件被两种后端先后
使用时，正是**可达**路径（用户先离线 ingest、后配置 LLM 再 search）。

**决策**：索引在 `meta` 表记录 `dim`（首个 put 时定档）；`put` / `search` 的向量维度与之不符时抛
`RAGError(INDEX_CORRUPT, "索引向量维度 N ≠ 当前 embedding 维度 M，须重建索引")` —— 复用既有错误码
（`INDEX_CORRUPT` 的规格语义本就是「索引损坏 → 降级重建或旧索引」），不新增错误码面。

**备选（不采纳）**：a) 静默跳过异维块 —— 检索**静默变空**，更难诊断；b) 每条向量各存各的维度、
混用共存 —— 索引语义分裂，且余弦跨维度无意义。

## 3. 决策：`RagService` 门面收口装配，而不是让 CLI 自己拼四个对象

CLI 三个子命令要复用同一套装配（embedder 选择 + 落盘路径 + 分块参数 + 生成融合）。若让 `entry`
自己 new 四个对象，装配知识就**渗进 CLI 层**（且与 `runtime` 各写一份 ⇒ 双真源）。

**决策**：`core/rag/service.py` 提供 `RagService`（组合 `IngestionPipeline` + `Retriever` + 可选
`RagGenerator`），暴露 `ingest(doc_id, content) -> int` / `refresh(...) -> bool` / `search(query, top_k)`
/ `ask(query, top_k)`；`build_runtime` 装配并挂 `runtime.rag`，`entry` 只调用门面。

- **生成器缺失时 `ask` 的错误口径**：新增错误码 `RAGErrorCode.GENERATION_UNAVAILABLE`（接口 §7 同步登记），
  由服务层显式抛出。**不**借用 `EMBEDDING_FAILED`（会把「无生成器」误标为 embedding 故障），
  **也不**抛裸 `RuntimeError`（契约要求结构化错误码，不向调用方抛裸异常）。
- **可达面事实（订正草案预期）**：`llm.api_key` / `provider` / `model` / `endpoint` 是 `validate_schema` 的
  **必需**项 ⇒ 空配置必然 `ConfigurationError`，`build_runtime` **走不到「未配 LLM」**，CLI 装配链因而
  **总有**生成器。所以「无生成器」的可达面是**服务层**（`RagService` 构造时 `generator=None`），CLI 侧的行为
  是把 RAG 结构化错误统一落 stderr 并给退出码 1（不静默给空答案、不抛裸栈）。

## 4. 决策：embedding 后端选择沿用 memory 既有裁决（语义优先、离线降级）

- 配 `llm.embedding_model` ⇒ `LLMEmbedder(StdlibLLMProvider(...))`（与 memory 通路同一 Provider 构造范式）；
- 未配 ⇒ `HashEmbedder()`（**离线降级基线**），且 CLI 打印一行降级提示（检索质量受限、维度和索引绑定）。

依据：memory 既有决策「HashEmbedder 是降级基线不完善，语义走 `LLMEmbedder`，**不引入本地语义模型**」
（见记忆 `rag-offline-embedder-decision`）。**不改 memory 的 `batch_embed(LLMEmbedder(...))` 通路。**

## 5. 决策：文档 `content_hash` 随索引落盘（跨进程增量判定才成立）

**问题**：`IngestionPipeline._hashes` 是**进程内** dict ⇒ 新进程里恒为空，`refresh` 永远判定「有变更」并
全量重建。而 CLI 每次调用都是**新进程**（两次 `rag ingest` 是两个进程），落盘增量判定否则形同不存在。

**决策**：`VectorStore` 抽象补一对方法 `record_document(doc_id, content_hash)` / `document_hash(doc_id)`
（`InMemoryVectorStore` 用 dict，`SqliteVectorStore` 落 `documents` 表），文档 hash 判定改由**存储侧**承载
⇒ 单一真源、跨进程成立；`IngestionPipeline._hashes` 字段删除（不留双真源）。同步把 `ingest` 语义合并为
**upsert**（返回本次写入块数，无变更返回 0），`refresh` 退化为 `ingest(...) > 0` 的布尔外壳 —— 既有方法面与
既有用例语义不变，重建前的 embedding 失败仍发生在 `delete` 之前（降级契约保持）。

## 6. 决策：不做 loop 注入、不做 ANN、不做索引并发隔离（明示不做）

`phase-22` §3.2(a) 只要求「补 CLI 入口 + 组合根装配，串成可用链路」。把 RAG 塞进 loop 推理链是**特性**
（会牵动 context 预算与 prompt 装配），本 change 不碰。规模未到 ANN 门槛，保持暴力余弦。
