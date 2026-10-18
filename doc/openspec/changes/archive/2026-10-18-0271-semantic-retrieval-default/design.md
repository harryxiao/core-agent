# Design 0271 — 语义检索默认化

## D1 推导放在「有效配置」属性，不回写字段

`LLMConfig.embedding_model` 保持**用户显式值**（空串 = 没写）。新增只读属性
`effective_embedding_model` 计算生效值：

```
显式 embedding_model 非空 ⇒ 用它（永远优先）
否则 embedding_auto 为真    ⇒ default_embedding_model(endpoint)（未命中 ⇒ ""）
否则                        ⇒ ""
```

这样：

- 热更新 `_merge_patch` 的基线仍取显式值 ⇒ 换端点后推导**自动跟随**，旧端点的推导值
  不会被当成用户显式声明固化下来；
- 用户随时写 `llm.embedding_model` 即可覆盖推导，零迁移；
- 测试与既有断言看 `embedding_model` 时语义不变（仍是「用户写了什么」）。

## D2 端点表：小、有据、可证伪

只收录**有据可查**的 OpenAI 兼容 embedding 端点（每项附来源口径），按主机名**精确或子域**
匹配（`host == domain` 或 `host.endswith("." + domain)`，大小写不敏感）：

| 端点主机 | 默认模型 | 依据 |
|---|---|---|
| `api.openai.com` | `text-embedding-3-small` | OpenAI Embeddings API 公开模型名 |
| `open.bigmodel.cn` | `embedding-3` | 智谱开放平台 Embedding-3（仓库手工 e2e 已用该名） |
| `dashscope.aliyuncs.com` | `text-embedding-v3` | 阿里云百炼文本向量模型 |
| `api.siliconflow.cn` | `BAAI/bge-m3` | SiliconFlow 模型广场 |

未命中（含 `api.deepseek.com` 等不提供 embedding 的端点、自建代理、本机地址）⇒ 返回空，
**不猜**。表不引入配置键，不是第二真源；显式配置永远胜出（与 `model_windows` 同纪律）。

## D3 开关与非法取值

`llm.embedding_auto` 缺省 **true**（「默认化」即本 change 的目标）。取值口径与 feature flag
同集（原生布尔 + `true/false`·`yes/no`·`on/off`·`1/0`），非法值在配置构建期抛
`ConfigurationError` 阻断启动（对齐 `show_thinking`；`bool("maybe")` 为真会静默开启）。

关闭开关 = 保留旧行为：有效模型为空 ⇒ 记忆词法、RAG `HashEmbedder`、启动提示照旧。

## D4 注入面：一个有效模型，两条通路共用

组合根沿用既有单一 `embed_provider`：有效模型非空 ⇒ 以该模型另构造
`StdlibLLMProvider`（复用 endpoint/api_key）→ 记忆走 `batch_embed(LLMEmbedder)`、RAG 走
`LLMEmbedder`；为空 ⇒ 记忆不注入 embedder、RAG 用 `HashEmbedder`。不新增 provider、
不改 `MemoryStore` / `RagService` 契约。

## D5 提示

- 有效模型为空：保留既有「词法匹配、语义检索未启用」stderr 提示（一次）。
- 有效模型来自推导（字段为空、属性非空）：输出一次「按端点自动选用 <model>（语义检索已启用；
  可用 llm.embedding_model 覆盖）」；不打印 endpoint / key。
- 显式配置：不额外提示（与既有行为一致）。

## D6 已知局限

1. 端点表是**静态**的：新端点/新模型名需改表（表中未命中只会退回词法，不会报错）。
2. 推导模型**不验证可用性**：首次检索若 404/超时，记忆侧按既有 `_embed_failed` 短路口径
   降级词法；RAG 侧按既有调用期降级。启动不被阻断，但首轮可能有一次失败网络往返。
3. 代理/自建网关无法识别端点语义 ⇒ 不推导；用户仍需显式配置。
4. 推导开启后首次语义检索会产生远端调用与费用（用户可用 `llm.embedding_auto=false` 关闭）。
