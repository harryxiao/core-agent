# RAG Specification Delta

## MODIFIED Requirements

### Requirement: 本地向量库存储
系统 SHALL 以本地嵌入式零服务向量库存储文档向量与索引：零服务、**零三方依赖**，无需独立 daemon 或
外部向量数据库；索引落盘于 `$CORE_STATE_DIR`，**跨进程复用**（一次 `ingest` 的成果在后续进程的检索中
可见）。**默认实现**为 stdlib `sqlite3` 嵌入式库（向量以 BLOB 存储、相似度在进程内计算）；`sqlite-vec`
等向量扩展在可得时经同一 `VectorStore` 抽象替换，调用方零改动。索引 SHALL 记录**向量维度**：
写入或检索的向量维度与索引不一致时（如更换 embedding 后端后沿用旧索引）SHALL 以**结构化错误**
拒绝并提示**重建索引**，SHALL NOT 静默截断比较（静默降级会产出无意义的相似度）。索引 SHALL 同时记录各文档的
`content_hash`（与向量同落盘），使**后续进程**的重复摄取按内容判定为**无变更**、不重复重建。

#### Scenario: 嵌入式零服务存储
- **GIVEN** 知识文档完成 embedding
- **WHEN** 向量写入向量库
- **THEN** 向量落盘于本地嵌入式向量库（默认 stdlib `sqlite3`），无需启动独立服务或外部向量数据库

#### Scenario: 索引跨进程复用
- **GIVEN** 一次 `ingest` 已把文档向量写入落盘索引
- **WHEN** 后续**另一个进程**装载同一索引并检索
- **THEN** 命中该文档的块（落盘索引为检索真源，不依赖进程内内存）

#### Scenario: 向量维度不一致时拒绝
- **GIVEN** 索引已按维度 N 建立（如缺省 HashEmbedder 的 128 维）
- **WHEN** 以维度 M（M≠N，如更换 embedding 后端）写入或检索
- **THEN** 以结构化错误（`INDEX_CORRUPT`）拒绝并提示重建索引，不产出错误相似度

### Requirement: 本地 Embedding
系统 SHALL **本地优先、零外呼**地生成 embedding：未配置 `llm.embedding_model` 时用 `HashEmbedder`
（字符 n-gram 哈希 → 确定性向量的**离线降级基线**，零三方依赖、不请求外部 embedding API）；
配置后经 llm-provider 归一化 embedding 入口调用远端模型，检索与调用方零改动。降级基线的**向量维度**
与远端模型不同，故索引按维度拒绝混用（见「本地向量库存储」）。

#### Scenario: 本地推理无外部依赖
- **GIVEN** 未配置远端 embedding 模型，一段文本需生成向量
- **WHEN** 调用 embedding 生成
- **THEN** 由本地 `HashEmbedder` 推理完成（确定性向量），不请求外部 embedding API

#### Scenario: 经 llm-provider 切换远端模型
- **GIVEN** 用户配置了远端 embedding 模型（`llm.embedding_model`）
- **WHEN** 经 llm-provider 归一化入口请求
- **THEN** 无缝切换到远端模型，检索与调用方无感知

### Requirement: 存储与 Embedding 依赖注入隔离
系统 SHALL 通过依赖注入隔离 VectorStore 与 Embedder 实现：替换向量库（如 stdlib `sqlite3` → 三方向量库）
或替换 embedding 后端（离线 `HashEmbedder` → 远端模型 / 换模型）时，检索与调用方零改动。

#### Scenario: 替换向量库实现
- **GIVEN** 需要替换向量库实现（如 stdlib `sqlite3` → Chroma）
- **WHEN** 注册新的 VectorStore 实现
- **THEN** Retriever 及所有调用方无需改动即可切换

#### Scenario: 替换 embedding 后端
- **GIVEN** 需要替换 embedding 后端（离线 `HashEmbedder` → 远端模型）
- **WHEN** 经 llm-provider 归一化入口或注册新的 Embedder 实现
- **THEN** 检索与调用方无感知切换
