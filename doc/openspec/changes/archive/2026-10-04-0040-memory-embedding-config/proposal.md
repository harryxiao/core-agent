# Change: 记忆 embedding 来源配置与装配（llm.embedding_model）

## Why

`0039-memory-multifactor-recall` 把记忆检索的**语义向量 seam** 备好（`MemoryStore` 接收
批量可调用 embedder、`build_runtime` 增 `embedder` DI 参数，默认 `None` → 词法），但**生产
侧无来源** → 语义检索仍不生效（遗留项 C7 的「接入」半边）。

embedding 来源有两个约束（ADR-0045）：① `StdlibLLMProvider.aembedding` 复用同一 provider
的模型名打 `/embeddings`（`stdlib_provider.py:168-176`），聊天模型通常不支持 embedding，
须**独立 embedding 模型**；② 配置旋钮属**横切 configuration 能力**，memory 能力不应感知
`embedding_model`（ADR-0040 MAL：memory 说抽象不说具体）。

## What Changes

- **配置旋钮**（configuration，MODIFIED「LLM 提供商配置（必选）」）：`llm` 段增**可选**子项
  `embedding_model`（复用 `endpoint` 与密钥引用；经 ConfigSpec 单一真源声明）；未设置或
  不可达时记忆检索回退词法，**不影响启动**。
- **组合根装配**（runtime）：`llm.embedding_model` 非空时，以该 model 构造独立 provider →
  `LLMEmbedder` → `batch_embed` → `MemoryStore(embedder=...)`；否则 `embedder=None`。
- **接口文档**：`03-interfaces/configuration-interface.md` 的 `llm` 段增 `embedding_model`。

## Non-goals

- 不改 `MemoryStore` / `relevance` / 排序公式（属 `0039`）。
- 不引入本地语义模型（sentence-transformers/BGE，ADR-0044 零三方依赖红线）。
- 密钥**只引用不读取**：embedding 复用 `llm.api_key_ref`，经 `resolve_secret` 注入并登记
  脱敏，不进日志/记忆。

## Impact

- **Affected specs**：`configuration/spec.md`（1 MODIFIED：「LLM 提供商配置（必选）」——增
  可选 `embedding_model` 子项 + 未设置回退词法场景）。
- **Affected docs**：`03-interfaces/configuration-interface.md`。
- **Affected code**：`src/core/configuration/models.py`（`LLMConfig.embedding_model`）+
  manager/ConfigSpec、`src/core/runtime.py`（按配置构造 embedder 注入）。
- **Dependencies**：`0039-memory-multifactor-recall`（提供 `embedder` seam 与
  `batch_embed`）；无新三方依赖。
- **风险**：低。默认未配置 → 词法路径不变；配置后走远端 embedding，不可达时静默降级词法
  （排障看日志）。
