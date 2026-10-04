# Design: 记忆 embedding 来源配置与装配

## 决策 1：配置旋钮归属 configuration（而非 memory）

`embedding_model` 是「选哪个模型做向量化」，属横切 configuration 的 ConfigSpec 单一真源
（ADR-0034）。memory 能力只声明「可注入 embedder」不感知来源（ADR-0040 MAL）。故配置 delta
落在 configuration spec，memory spec 不动——两个能力的变化域解耦，可归因性清晰。

## 决策 2：独立 provider，而非复用聊天 provider

`StdlibLLMProvider.aembedding` 用构造时的 `model` 打 `/embeddings`；聊天模型名打 embedding
端点通常 404/400。故设置 `embedding_model` 时**另构造一个** `StdlibLLMProvider(model=
embedding_model, base_url=同 endpoint, api_key=同引用)` → `LLMEmbedder` → `batch_embed` →
`MemoryStore(embedder=...)`。密钥经 `resolve_secret` 注入一次并登记脱敏。

## 决策 3：未配置即回退，不改启动契约

`embedding_model` 为**可选**：未设置 → `embedder=None` → 0039 的词法路径；不可达 → 调用期
异常由 `relevance` 内建 try/except 降级（`relevance.py:64-70`）。启动不被 embedding 的
可用性阻断（对齐「LLM 配置必选、增强项可选」的既有分层）。

## 风险与缓解

- **远端依赖**：embedding 需网络/额度；不可达静默降级词法 → 排障须看日志（tasks 覆盖日志
  断言）；隔离在本次薄变更，不回灌 0039。
- **成本**：每 read 至多 1 次 query 向量化 + 未变条目复用缓存（0039 已定），调用量有界。
