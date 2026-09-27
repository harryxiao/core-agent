# Design

## Context

RAG 调研（research_findings.md）确认：本地向量库首选 sqlite-vec（嵌入式零服务、零外部依赖，与 Core-Agent 既有 SQLite 生态统一）；embedding 用 sentence-transformers + BGE（本地推理、无需外部 API）。RAG 管「知识文档」语义检索，codebase-memory-mcp 管「代码结构」结构化理解，二者正交互补、同时引入。本 design 明确 rag 层的存储、摄取、检索、生成融合链路与职责边界，作为模块/接口文档与实现的依据。

## Decisions

- **向量库选 sqlite-vec**：嵌入式零服务，与既有 SQLite 生态统一；无需独立 daemon 或外部向量数据库。
- **embedding 用 sentence-transformers + BGE 本地推理**：无需外部 embedding API；可经 llm-provider 归一化 embedding 入口切换到远端模型。
- **生成融合经 context 装配器**：检索片段按 context 预算裁剪后注入提示词；检索无结果降级纯 LLM 生成。
- **职责边界**：RAG 管知识文档语义检索，codebase-memory-mcp 管代码结构理解，互补不重叠、同时引入。

## Risks / Trade-offs

- **sqlite-vec vs LanceDB**：sqlite-vec 生态统一但复杂查询/多模态弱于 LanceDB；若未来多模态向量需求强，再评估切换。
- **本地 embedding 资源占用**：BGE 本地推理占用内存/CPU，需评估模型量化与缓存策略；可经 llm-provider 切远端模型兜底。
- **索引一致性**：文档变更需增量重建，重建窗口期检索可能返回旧结果，已按降级策略兜底。

## Open Questions

- 是否首期支持 bge-m3 多语言/多模态 embedding，还是先 BGE 单语。
- 向量库与索引是否纳入 permission 沙箱保护范围（沙箱颗粒度 P1 扩展）。
- 检索 top-k 与 context 预算的动态联动策略（超预算时裁剪顺序）。
