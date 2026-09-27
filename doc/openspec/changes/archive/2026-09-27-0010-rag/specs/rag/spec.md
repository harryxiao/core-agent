RAG（检索增强生成）让 Core-Agent 通过本地向量库语义检索知识文档、弥补 LLM 知识缺口：以 sqlite-vec 嵌入式零服务向量库存储文档向量，sentence-transformers + BGE 本地推理生成 embedding，检索器按向量相似度取 top-k 片段，经 context 装配器注入上下文、由 llm-provider 生成。职责边界：RAG 管「知识文档」语义检索，codebase-memory-mcp 管「代码结构」结构化理解，二者正交互补（来源：research_findings.md，2026-09-20）。

## ADDED Requirements

### Requirement: 本地向量库存储
系统 SHALL 以 sqlite-vec 作为本地嵌入式向量库存储文档向量与索引：零服务、零外部依赖，与既有 SQLite 生态统一，无需独立 daemon 或外部向量数据库。

#### Scenario: 嵌入式零服务存储
- **GIVEN** 知识文档完成 embedding
- **WHEN** 向量写入向量库
- **THEN** 向量落盘于本地 SQLite 向量扩展，无需启动独立服务或外部向量数据库

### Requirement: 文档摄取与分块
系统 SHALL 提供文档摄取管线：导入知识文档 → 分块 → 生成 embedding → 建立向量索引，并支持增量更新与索引失效检测。

#### Scenario: 文档导入建索引
- **GIVEN** 一份知识文档待导入
- **WHEN** 摄取管线处理该文档
- **THEN** 文档被分块、逐块生成 embedding 并建立向量索引，可被检索

#### Scenario: 源文档变更触发增量更新
- **GIVEN** 源文档内容变更
- **WHEN** 检测到 hash 不一致
- **THEN** 触发受影响块的增量重建，期间该文档检索降级为旧索引

#### Scenario: 摄取/重建失败降级
- **GIVEN** 摄取管线在 embedding 生成、索引写入或重建过程中失败（如 embedding 失败、索引损坏、重建失败）
- **WHEN** 摄取或重建出错
- **THEN** 该文档检索降级为旧索引（或纯 LLM 生成），记录失败并可重试，不阻断主流程

### Requirement: 本地 Embedding
系统 SHALL 用 sentence-transformers + BGE 在本地推理生成 embedding，无需外部 API；可经 llm-provider 归一化 embedding 入口切换远端模型，调用方零改动。

#### Scenario: 本地推理无外部依赖
- **GIVEN** 一段文本需生成向量
- **WHEN** 调用 embedding 生成
- **THEN** 由本地 sentence-transformers + BGE 推理完成，不请求外部 embedding API

#### Scenario: 经 llm-provider 切换远端模型
- **GIVEN** 用户配置了远端 embedding 模型
- **WHEN** 经 llm-provider 归一化入口请求
- **THEN** 无缝切换到远端模型，检索与调用方无感知

### Requirement: 语义检索
系统 SHALL 按向量相似度检索 top-k 最相关片段、弥补 LLM 知识缺口，检索结果带相关度得分供后续裁剪排序。

#### Scenario: top-k 相似度检索
- **GIVEN** 一条查询语句
- **WHEN** 执行语义检索
- **THEN** 返回按向量相似度排序的 top-k 片段及相关度得分

### Requirement: 生成融合
系统 SHALL 将检索片段作为上下文注入生成链路：经 context 装配器按预算裁剪后随提示词送入 llm-provider 生成，检索缺失时降级为纯 LLM 生成。

#### Scenario: 检索上下文注入生成
- **GIVEN** 检索返回若干相关片段
- **WHEN** 构建生成请求
- **THEN** 片段经 context 装配器按预算裁剪后注入提示词，由 llm-provider 生成

#### Scenario: 检索无结果降级
- **GIVEN** 语义检索无相关片段
- **WHEN** 构建生成请求
- **THEN** 降级为纯 LLM 生成，不阻断流程

### Requirement: 与 CodeBase Engine 职责边界
系统 SHALL 保持 RAG 与 codebase-memory-mcp 的互补分工：RAG 管「知识文档」语义检索，codebase-memory-mcp 管「代码结构」结构化理解，两者同时引入、互不重叠。

#### Scenario: 文档与代码各归其位
- **GIVEN** 一次既涉及知识文档又涉及代码结构的查询
- **WHEN** 检索执行
- **THEN** 文档语义检索走 RAG，代码结构/符号/调用链理解走 codebase-memory-mcp
