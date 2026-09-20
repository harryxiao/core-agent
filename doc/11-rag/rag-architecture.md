# 检索增强生成：让 Core-Agent 检索本地知识文档补 LLM 知识缺口

> 对应规格：`doc/openspec/specs/rag/spec.md` ｜ 变更提案：`doc/openspec/changes/0010-rag/`
> 本方案文档对应 ADR-0025

---

## 1. 定位与场景

LLM 存在知识缺口：训练截止、私有/领域知识缺失。RAG（检索增强生成）让 Core-Agent 通过本地向量库语义检索知识文档，把最相关片段作为上下文注入生成链路，弥补 LLM 知识缺口。

- **知识文档**：产品文档 / 领域知识 / 内部规范 / 会议纪要等「知识文档」的语义检索。
- **与 codebase-memory-mcp 分工**：RAG 管「知识文档」语义检索，codebase-memory-mcp 管「代码结构」结构化理解，二者正交互补、同时引入。

## 2. 架构

调研（`research_findings.md`，2026-09-20）确认：向量库选 sqlite-vec（嵌入式零服务），embedding 用 sentence-transformers + BGE（本地推理）。

```
摄取管线   知识文档 → 分块 → embedding → 向量索引
             （sentence-transformers + BGE 本地推理）
存储       sqlite-vec 嵌入式零服务向量库（与 SQLite 生态统一）
检索       查询 embedding → 向量相似度 top-k 片段 + 相关度得分
生成融合    检索片段 → context 装配器按预算裁剪 → llm-provider 生成
```

- **向量库**：sqlite-vec，嵌入式零服务、零外部依赖，与 Core-Agent 既有 SQLite 生态统一，无需独立 daemon。
- **embedding**：sentence-transformers + BGE 本地推理，无需外部 API；可经 llm-provider 归一化 embedding 入口切换到远端模型。

## 3. 数据流

1. **文档导入**：摄取管线分块 → 本地 embedding → 建立向量索引（增量更新 + hash 失效检测）。
2. **查询**：查询语句 embedding → 向量相似度 top-k 检索，返回片段 + 相关度得分。
3. **生成**：检索片段经 context 装配器按预算裁剪 → 注入提示词 → llm-provider 生成。
4. **降级**：检索无结果 → 纯 LLM 生成，不阻断流程。

## 4. 接口设计

| 接口 | 职责 |
|---|---|
| `VectorStore` | sqlite-vec 向量 CRUD + 索引（嵌入式，零服务） |
| `IngestionPipeline` | 文档导入 → 分块 → embedding → 索引；增量更新 + hash 失效检测 |
| `Embedder` | 本地 sentence-transformers + BGE 推理；经 llm-provider 归一化入口可切远端 |
| `Retriever` | 向量相似度 top-k 检索，返回片段 + 相关度得分 |
| `RagGenerator` | 检索片段注入生成链路，经 context 装配器裁剪，检索缺失降级纯 LLM |

## 5. 与其他模块的关系

| 模块 | 关系 |
|---|---|
| llm-provider | 复用：embedding 归一化入口 + 生成 |
| context | 复用：上下文装配器按预算裁剪注入 |
| memory | 复用：知识文档与向量索引的持久化落盘 |
| codebase-memory-mcp | 互补：RAG 管知识文档，其管代码结构，不重叠 |

## 6. ADR 索引

| ADR | 决策 |
|---|---|
| ADR-0025 | RAG 采用 sqlite-vec 本地向量库 + sentence-transformers/BGE 本地 embedding |
