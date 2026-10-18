# rag — 语义检索默认化（change 0271）

## MODIFIED Requirements

### Requirement: 本地 Embedding
系统 SHALL **本地优先、零外呼**地生成 embedding：**有效 embedding 模型为空**时（既未显式配置
`llm.embedding_model`，也未按 `llm.embedding_auto` 从已知端点推导出模型）用 `HashEmbedder`
（字符 n-gram 哈希 → 确定性向量的**离线降级基线**，零三方依赖、不请求外部 embedding API）；
有效模型非空时（显式配置，或按端点表推导）经 llm-provider 归一化 embedding 入口调用远端模型，
检索与调用方零改动。降级基线的**向量维度**与远端模型不同，故索引按维度拒绝混用
（见「本地向量库存储」）。

#### Scenario: 本地推理无外部依赖
- **GIVEN** 无有效 embedding 模型（未配置且未推导 / 推导关闭），一段文本需生成向量
- **WHEN** 调用 embedding 生成
- **THEN** 由本地 `HashEmbedder` 推理完成（确定性向量），不请求外部 embedding API

#### Scenario: 经 llm-provider 切换远端模型
- **GIVEN** 用户显式配置了远端 embedding 模型（`llm.embedding_model`）
- **WHEN** 经 llm-provider 归一化入口请求
- **THEN** 无缝切换到远端模型，检索与调用方无感知

#### Scenario: 端点推导启用远端 embedding
- **GIVEN** 未显式配置 `llm.embedding_model`，`embedding_auto` 为缺省开启且 endpoint 主机命中
  内置端点表
- **WHEN** 系统装配 RAG
- **THEN** 以推导模型经 llm-provider 归一化入口生成 embedding（不再使用 `HashEmbedder`），
  检索与调用方零改动
