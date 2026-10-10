# llm-provider 规格 delta：流式令牌用量与请求侧输出上限（change 0183）

## ADDED Requirements

### Requirement: 流式增量携带令牌用量

流式增量模型 `LLMChunk` SHALL 携带 `usage` 字段（类型 `TokenUsage | None`；该增量块未携带用量时
为 `None`，SHALL NOT 以零值冒充实报）。provider 归一化 SHALL 从流式增量块的顶层 `usage` 对象取值
（OpenAI 兼容端点在**开启用量上报**时于**末块**携带，该末块的 `choices` 可为**空数组** —— 归一化
SHALL 在此形态下仍然产出携带 `usage` 的增量块，SHALL NOT 因 `choices` 为空而丢弃用量）；
往返字段缺失（无 `usage`、或 `usage` 为 `null`）SHALL 归一为 `None`，SHALL NOT 报错。
归一化 SHALL NOT 改变 `content` / `tool_calls` / `thinking` / `finish_reason` 的既有语义，
亦 SHALL NOT 改变**非流式** `LLMResponse.usage` 的既有解析（缺省零值口径逐字保留）。

provider 在**流式**请求上 SHALL 要求端点上报用量（OpenAI 兼容 `stream_options.include_usage`），
且 SHALL NOT 对**非流式**请求下发该字段（非流式响应本就携带 `usage`）。

消费方（`LLMPlanner`）SHALL 在流式路径上消费该用量：`prompt_tokens` SHALL 与装配估算取**较大者**
作为提示词占用的**下界**（与既有非流式口径逐字一致），`completion_tokens` SHALL 仅作**观测**记录，
SHALL NOT 参与任何判定（终止语义 / 预算闸门均不改）。

#### Scenario: 流式末块携带用量

- **GIVEN** provider 流式返回若干增量块，其中末块 `choices` 为空数组且顶层携带
  `usage = {"prompt_tokens": 120, "completion_tokens": 34}`
- **WHEN** 归一化为 `LLMChunk`
- **THEN** 该增量块 `usage` 为 `TokenUsage(prompt_tokens=120, completion_tokens=34)`，其 `content`
  为空串，其余字段不受影响

#### Scenario: 未携带用量的增量块为 None

- **GIVEN** 某增量块不含顶层 `usage`（或该值为 `null`）
- **WHEN** 归一化该增量块
- **THEN** `LLMChunk.usage` 为 `None`（不报错，也不以 `TokenUsage(0, 0)` 冒充），其余字段解析与
  既有实现逐字一致

#### Scenario: 流式请求要求端点上报用量

- **GIVEN** 一次流式调用
- **WHEN** provider 构建请求体
- **THEN** 请求体携带 `stream: true` 与 `stream_options.include_usage: true`；**非流式**请求体
  不携带 `stream_options`（逐字保留既有形状）

#### Scenario: 消费方以实报抬升提示词下界且不改判定

- **GIVEN** 装配估算为 `E`，末块实报 `prompt_tokens = P`
- **WHEN** 流式推理结束
- **THEN** 提示词观测为 `max(E, P)`（实报为**下界**、只抬升）；`completion_tokens` 可经观测探针读取，
  但不改变终止语义与预算闸门

### Requirement: 请求侧输出上限按预留注入

统一补全请求 `LLMRequest.max_tokens` SHALL 由组合根按**输出预留**（`loop.output_reserve`）注入：
`LLMPlanner` SHALL 提供构造期注入点，取值 **> 0** 时 SHALL 填入每次请求的 `max_tokens`（provider
据此下发 `max_tokens`）；注入点缺省 `None` **或**取值 **≤ 0** 时 SHALL NOT 下发该字段（既有请求形状
逐字不变 —— 端点不支持 / 上限更低时零影响）。

该注入使「预留」从**记账假设**变为**端点上界**：预算派生（`窗口 − 预留`）本已假设输出至多占预留
这么多 token，下发后模型侧不再可能越界产出 ⇒ 记账与实际上界一致。

#### Scenario: 注入正预留即下发输出上限

- **GIVEN** `LLMPlanner` 经构造注入 `max_tokens = 8192`
- **WHEN** 构建补全请求
- **THEN** 请求 `max_tokens` 为 `8192`，provider 请求体携带 `max_tokens: 8192`

#### Scenario: 未注入或非正预留不下发

- **GIVEN** `LLMPlanner` 未注入 `max_tokens`（缺省），或注入值 `≤ 0`
- **WHEN** 构建补全请求
- **THEN** 请求 `max_tokens` 为 `None`，provider 请求体**不含** `max_tokens` 键（与既有实现逐字一致）
