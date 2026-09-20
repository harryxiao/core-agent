# Change: RAG 检索增强生成（本地向量库语义检索）

## Why

LLM 存在知识缺口（训练截止、私有/领域知识缺失），Core-Agent 需通过检索本地向量库补充知识。调研（research_findings.md，2026-09-20）确认：本地向量库首选 **sqlite-vec**（嵌入式零服务，与 Core-Agent 既有 SQLite 生态统一），embedding 用 **sentence-transformers + BGE**（本地推理，无需外部 API）。RAG 管「知识文档」语义检索，与 codebase-memory-mcp 管「代码结构」结构化理解正交互补、同时引入。

## What Changes

- 新增 `rag` capability：本地向量库（sqlite-vec）+ 文档摄取分块 + 本地 embedding（sentence-transformers + BGE）+ 语义检索 + 生成融合
- 明确职责边界：RAG（知识文档语义检索）与 codebase-memory-mcp（代码结构理解）互补不重叠
- 与 `llm-provider`（embedding 归一化入口 + 生成）和 `context`（上下文装配器注入）协作

## Impact

- **Affected specs**：`rag`（新增 capability）
- **Affected docs**：`11-rag/rag-architecture.md`（新增，含架构说明）、`README.md`（索引）
- **Affected code**：无（本 change 声明检索增强生成层行为，具体实现由后续步骤确定）
- **Dependencies**：复用 `llm-provider`（embedding 归一化入口 + 生成）、`context`（上下文装配器按预算裁剪注入）；与 codebase-memory-mcp（经 MCP 接入）互补不重叠
