去具体化与依赖注入隔离：向量库与 embedding 后端降级为「默认实现」，经 VectorStore / Embedder 抽象接口与依赖注入隔离，替换向量库或 embedding 后端调用方零改动。（来源：架构审计 MAL 约定，2026-09-27）

## ADDED Requirements

### Requirement: 存储与 Embedding 依赖注入隔离
系统 SHALL 通过依赖注入隔离 VectorStore 与 Embedder 实现：替换向量库（如 sqlite-vec → Chroma）或替换 embedding 后端（本地 → 远端 / 换模型）时，检索与调用方零改动。

#### Scenario: 替换向量库实现
- **GIVEN** 需要替换向量库实现（如 sqlite-vec → Chroma）
- **WHEN** 注册新的 VectorStore 实现
- **THEN** Retriever 及所有调用方无需改动即可切换

#### Scenario: 替换 embedding 后端
- **GIVEN** 需要替换 embedding 后端（本地 BGE → 远端模型）
- **WHEN** 经 llm-provider 归一化入口或注册新的 Embedder 实现
- **THEN** 检索与调用方无感知切换

## MODIFIED Requirements

### Requirement: 本地向量库存储
系统 SHALL 以本地嵌入式零服务向量库存储文档向量与索引：零服务、零外部依赖，与既有 SQLite 生态统一，无需独立 daemon 或外部向量数据库。默认实现为 sqlite-vec，经 VectorStore 抽象接口隔离，替换向量库实现时调用方零改动。

#### Scenario: 嵌入式零服务存储
- **GIVEN** 知识文档完成 embedding
- **WHEN** 向量写入向量库
- **THEN** 向量落盘于本地嵌入式向量库（默认 SQLite 向量扩展），无需启动独立服务或外部向量数据库

### Requirement: 本地 Embedding
系统 SHALL 用本地 embedding 模型在本地推理生成 embedding（默认 sentence-transformers + BGE），无需外部 API；可经 llm-provider 归一化 embedding 入口切换远端模型，调用方零改动。

#### Scenario: 本地推理无外部依赖
- **GIVEN** 一段文本需生成向量
- **WHEN** 调用 embedding 生成
- **THEN** 由本地 embedding 模型（默认 sentence-transformers + BGE）推理完成，不请求外部 embedding API

#### Scenario: 经 llm-provider 切换远端模型
- **GIVEN** 用户配置了远端 embedding 模型
- **WHEN** 经 llm-provider 归一化入口请求
- **THEN** 无缝切换到远端模型，检索与调用方无感知
