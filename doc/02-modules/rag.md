# 模块设计：检索增强生成（Retrieval-Augmented Generation, RAG）

> 对应规格：`doc/openspec/specs/rag/spec.md` ｜ 接口：`doc/03-interfaces/rag-interface.md`
> 定位：**L3 检索底座**，以本地向量库做知识文档的语义检索，弥补 LLM 训练截止 / 私有领域知识缺口。

---

## 1. 模块定位

LLM 存在固有知识缺口：训练截止、私有/领域知识缺失。RAG（检索增强生成）让 Core-Agent 通过本地向量库语义检索知识文档（产品文档、领域知识、内部规范等），把最相关片段作为上下文注入生成链路，使回答基于本地知识库而非仅凭模型参数。

职责边界：RAG 管「知识文档」的**语义检索**，codebase-memory-mcp 管「代码结构」的**结构化理解**，二者正交互补、同时引入。

---

## 2. 内部组成

```
RAG（L3）
├── VectorStore        向量存储：sqlite-vec 嵌入式向量 CRUD + 索引
├── IngestionPipeline  摄取管线：文档导入 → 分块 → embedding → 索引（增量更新）
├── Embedder           本地 embedding：sentence-transformers + BGE 推理
├── Retriever          语义检索：查询 embedding → 向量相似度 top-k
└── RagGenerator       生成融合：检索片段注入 → llm-provider 生成（无结果降级）
```

---

## 3. 关键设计

### 3.1 嵌入式零服务存储

- 向量库选 **sqlite-vec**：嵌入式、零服务、零外部依赖，与 Core-Agent 既有 SQLite 生态统一，无需独立 daemon 或外部向量数据库。
- 契合「无特权核心」原则，不引入特权服务；`VectorStore` 负责向量 CRUD 与索引，落盘即持久化。
- 对比 LanceDB（同为嵌入式、多模态更强）作为未来扩展点——若多模态向量需求强再评估切换，不属本期范围。

### 3.2 摄取与增量更新

- 摄取管线：`IngestionPipeline.ingest` 将知识文档 **分块 → 逐块 embedding → 写入向量索引**。
- 增量更新：`refresh` 按 `content_hash` 检测源文档变更，不一致则重建受影响块；重建窗口期该文档检索**降级旧索引**，不阻塞查询。
- 摄取/重建失败降级：记录失败、可重试，不阻断主流程。

### 3.3 本地 embedding 与远端切换

- `Embedder` 默认用 **sentence-transformers + BGE** 本地推理生成向量，不请求外部 embedding API。
- 可经 **llm-provider 归一化 embedding 入口**切换到远端模型，检索与调用方零改动。

### 3.4 语义检索

- `Retriever.search`：查询语句 embedding → 向量相似度 **top-k** 检索，返回片段 + 相关度得分（降序），供后续裁剪排序。

### 3.5 生成融合与降级

- `RagGenerator.generate`：检索片段经 **context 装配器按预算裁剪**后注入提示词 → llm-provider 生成。
- 检索无结果时**降级纯 LLM 生成**，不阻断流程。

---

## 4. 与 codebase-memory-mcp 的分工

| 维度 | RAG | codebase-memory-mcp |
|---|---|---|
| 对象 | 知识文档（产品/领域/规范） | 代码结构（symbol / 依赖 / 调用图） |
| 手段 | 向量库 + embedding 语义相似度 | AST + LSP 结构化理解（确定性） |
| 结果 | top-k 片段 + 相关度得分 | 符号 / 依赖 / 调用链 |

文档语义检索走 RAG，代码结构理解走 codebase-memory-mcp，一次查询中两者各归其位、互不重叠。

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| embedding 生成失败 | 返回 `EMBEDDING_FAILED`，该文档检索降级旧索引或纯 LLM |
| 向量索引损坏 | 返回 `INDEX_CORRUPT`，降级重建或回退旧索引 |
| 增量重建失败 | 返回 `REBUILD_FAILED`，降级旧索引，可重试 |
| 检索无结果 | 返回空列表，降级纯 LLM 生成，不阻断 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/rag-interface.md`
- 规格：`doc/openspec/specs/rag/spec.md`
- 架构：`doc/11-rag/rag-architecture.md`（ADR-0025、数据流）
- 变更：`doc/openspec/changes/0010-rag/`
- 上游：`doc/02-modules/llm-provider.md`（embedding 归一化入口 + 生成）、`doc/02-modules/context.md`（上下文装配裁剪）
