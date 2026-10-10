# 变更提案 — 流式令牌用量与请求侧输出上限（change 0183）

## 为什么

`known-risk.md` §1 **E97** 余项之一（会同「内置 known-model 窗口表」与「`llm.provider` 死标签」构成
`Phase 35` #4 `0184` 的兄弟项）—— **流式路径的用量上报整条链路缺席**：

- `LLMChunk`（`src/core/llm_provider/models.py:78-87`）**无** `usage` 字段，`_map_chunk`
  （`src/core/llm_provider/stdlib_provider.py:260-272`）从不解析端点的用量对象
  ⇒ 端点实报的 `prompt_tokens` **进不了**内核。
- 流式是**默认路径**（`loop/default.py` 的 `_reason_events` 优先走 `planner.astream`；非流式只在
  缺 `astream` 时退化）⇒ `LLMPlanner._last_prompt_tokens` 在流式下**只有装配估算**、**从不**被实报
  抬升（非流式路径在 `_complete` 里已抬升，两路径口径不一致）。
- 流式请求体**不要求**端点上报用量（无 `stream_options.include_usage`）⇒ 即便解析了字段，端点也
  不会在末块给出。
- `LLMRequest.max_tokens`（`models.py:26`）是**死字段**：`_build_body` 已支持下发
  （`stdlib_provider.py:212-213`），但**无任何调用方填它**（`planner._build_request` 不传）
  ⇒ 「输出预留」（`loop.output_reserve`）只是**记账假设**，模型侧无上界。
- `completion_tokens`（`TokenUsage` 的另一半）在内核**无人消费**。

后果：token 记账的**下界**在流式（默认）路径上永远偏保守（估算覆盖装配、但拿不到端点实报）；
「输出预留」与实际上界脱节；流式的完成用量对观测面不可见。

## 改什么

| 面 | 变更 |
|---|---|
| `llm_provider/models.py` | `LLMChunk.usage: TokenUsage \| None = None` |
| `llm_provider/stdlib_provider.py` | 流式请求体增 `stream_options={"include_usage": True}`；`_map_chunk` 解析顶层 `usage`（**`choices` 为空数组的末块也要产出用量块**）；新增 `_map_usage` 归一（缺失 / `null` ⇒ `None`） |
| `loop/planner.py` | `astream` 消费 `chunk.usage`：`_last_prompt_tokens = max(估算, prompt_tokens)`（与非流式同口径）；记录 `_last_completion_tokens` 并新增观测探针；构造期新增 `max_tokens` 注入点（> 0 才下发），`_build_request` 填入 `LLMRequest` |
| `configuration/manager.py` | 新增 `output_reserve()` 独立访问器（键已存在，**无**新配置键、**无**规格变更） |
| `runtime.py` | `LLMPlanner(..., max_tokens=config.output_reserve())` |
| 规格 | `llm-provider` **ADDED** ×2：「流式增量携带令牌用量」+「请求侧输出上限按预留注入」（各含 Scenario） |
| 测试 | provider 侧（用量归一三态 + 请求体形状）、planner 侧（实报抬升下界 / 完成用量观测 / `max_tokens` 注入与非正不下发） |

## 影响

- **行为变更（有意）**：请求体在**流式**下多一个 `stream_options` 字段。**局限**：拒绝该字段的
  端点会在流式路径报错（走既有 `LLMError` 路径，**响亮失败**、非静默）；OpenAI 兼容生态（OpenAI /
  Azure / DeepSeek / Moonshot / GLM / vLLM / Ollama 兼容层）普遍接受。
- **行为变更（有意）**：`max_tokens` 在注入点 > 0 时下发。组合根注入 `loop.output_reserve`
  （缺省 `8192`）⇒ 默认即下发。**局限**：模型输出上限低于预留值时端点会 400（响亮失败）；键本是
  既有配置项，值不对时预算派生**本已**错误 ⇒ 本条让配置错误提前暴露在端点上。注入点缺省 `None`
  ⇒ 其他构造点（第三方 / 测试替身）**逐字不变**。
- **向后兼容**：非流式 `LLMResponse.usage` 解析、`LLMChunk` 其余字段语义、终止语义与预算闸门
  **逐字不变**；`completion_tokens` 仅入观测面，**不参与**判定。
- 无新增第三方依赖；无 import 方向变化；`exclude_source_prefixes=("beast.","pet")` **逐字不动**。
