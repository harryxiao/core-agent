# Proposal 0271 — 语义检索默认化（Claude Code 对齐建议 5a）

## Why

当前记忆检索的语义能力是**显式配置才启用**：`llm.embedding_model` 为空 ⇒ 组合根不注入
embedder ⇒ `MemoryStore` 恒走词法，CLI 每次启动打印「语义检索未启用」。真实用户配置里
`llm.embedding_model` 往往不写（例如智谱端点 `open.bigmodel.cn` 明明提供 `embedding-3`），
于是向量召回这项能力**默认不在场**——不是模型不支持，而是配置面要求用户知道并手写一个
与聊天模型无关的模型名。

`llm.context_window` 已经采用「未配置时按已知模型表推导、显式配置永远优先」的口径
（change 0184 / ADR-0175）。embedding 模型可以采用同一形态：**按端点推导默认值**，
用户不改配置也能获得语义召回；不认识的端点仍按词法降级，不猜测。

## What Changes

- 新 `src/core/configuration/embedding_models.py`：**已知端点 → 默认 embedding 模型**表
  （仅收录有据可查、OpenAI 兼容 `/embeddings` 的端点；未命中返回空 = 不猜）。
- `LLMConfig` 增 `embedding_auto: bool = True` 与只读属性 `effective_embedding_model`：
  显式 `embedding_model` 优先；否则 `embedding_auto` 开启时按端点表推导；关闭/未命中 ⇒ 空。
- 新配置项 `llm.embedding_auto`（CLI `--llm-embedding-auto` / env
  `CORE_LLM_EMBEDDING_AUTO` / yaml `llm.embedding_auto`，缺省 `true`；取值口径与 feature
  flag 同集，非法取值校验期阻断启动）。
- 组合根与 CLI 提示改用**有效模型**：有显式或推导值时注入 `LLMEmbedder`（记忆与 RAG
  共用），无有效值时保持词法 / `HashEmbedder` 降级并保留启动提示；推导值额外给一次
  「按端点自动选用 …（可用 `llm.embedding_model` 覆盖）」提示。

## Impact

- 代码：`src/core/configuration/{embedding_models.py(新),models.py,manager.py}`、
  `src/core/runtime.py`、`src/core/entry.py`。
- 测试：新增 `tests/test_semantic_default.py`；`tests/test_entry.py` 补推导/关闭两条提示用例。
- 规格：`configuration` MODIFIED「LLM 提供商配置（必选）」；`memory` MODIFIED「温度分层检索」；
  `rag` MODIFIED「本地 Embedding」。
- 兼容：显式 `embedding_model` 行为不变；不认识的端点 / `embedding_auto=false` ⇒ 有效模型为空，
  与引入前**逐字一致**（词法 / HashEmbedder + 启动提示）；推导只影响**有效配置**，不回写
  yaml、不改变 `llm.embedding_model` 字段本身的显式值。

## 不做（明确边界）

- 不引入本地语义模型 / 三方向量库；推导仍走 `LLMEmbedder`（远端 OpenAI 兼容 `/embeddings`）。
- 不做 `/models` 探测或运行时自动发现：推导是**确定性端点表**，无启动网络调用、无额外延迟。
- 不把推导值写回用户配置文件；不改变显式配置的热更新语义。
- 不新增 embedding 专用超时键；远端不可达仍由既有调用期降级兜底（首次失败后短路为词法）。
