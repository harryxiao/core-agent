# Tasks

## 1. 最小闭环（P0）

- [x] 1.1 本地向量库接入（向量 CRUD + 索引；默认 InMemoryVectorStore，经 VectorStore 抽象可切换 sqlite-vec）
- [x] 1.2 文档摄取与分块管线（导入 → 分块 → embedding → 索引）
- [x] 1.3 本地 embedding（默认 HashEmbedder 零依赖哈希；经 llm-provider 可切远端语义模型，本地 BGE 预留）
- [x] 1.4 向量相似度 top-k 语义检索

## 2. 生成融合（P1）

- [x] 2.1 检索片段经 context 装配器按预算裁剪后注入提示词
- [x] 2.2 经 llm-provider 归一化 embedding 入口切换远端模型
- [x] 2.3 检索无结果降级纯 LLM 生成
