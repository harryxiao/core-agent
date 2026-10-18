# llm-provider — 输出上限能力适配与终止原因归一（change 0293）

## MODIFIED Requirements

### Requirement: 流式增量携带终止原因

流式增量模型 `LLMChunk` SHALL 携带 `finish_reason` 字段（字符串；该增量块未携带该信息时为空串，
SHALL NOT 以缺省值报错）。provider 归一化 SHALL 从流式增量块的 `choices[0].finish_reason` 取值
（OpenAI 兼容端点通常在**末块**携带，取值如 `stop` / `length`），SHALL NOT 因该字段缺失而丢弃该块
或改写其余字段。归一化 SHALL NOT 改变 `content` / `tool_calls` / `thinking` 的既有语义。

provider 归一化 SHALL 将各协议的**截断别名**归一为 `length`：`max_tokens`、`MAX_TOKENS`、
`max_output_tokens`（大小写不敏感，允许首尾空白）。其余取值（`stop`、`content_filter`、未知值）
SHALL 原样保留，SHALL NOT 折叠为 `stop`；缺失时沿用既有口径（流式为空串，非流式为 `stop`）。
该归一 SHALL 同时作用于流式 `LLMChunk` 与非流式 `LLMResponse`。

「终止原因」是消费方（如循环的推理解析）判定**输出是否被 provider 截断**的权威信号；
该字段 SHALL 仅供归因与提示，SHALL NOT 参与内容拼装。

#### Scenario: 流式末块携带终止原因

- **GIVEN** provider 流式返回若干增量块，其中末块携带 `choices[0].finish_reason = "length"`
- **WHEN** 归一化为 `LLMChunk`
- **THEN** 该 `LLMChunk.finish_reason` 为 `"length"`，且其 `content` / `tool_calls` / `thinking` 逐字不受影响

#### Scenario: 未携带终止原因的增量块为零值

- **GIVEN** 某增量块不含 `finish_reason`（既有行为）
- **WHEN** 归一化该增量块
- **THEN** `LLMChunk.finish_reason` 为空串，不报错，其余字段解析与既有实现逐字一致

#### Scenario: 截断别名归一为 length

- **GIVEN** 非流式响应携带 `finish_reason = "MAX_TOKENS"`，或流式末块携带
  `finish_reason = "max_tokens"`
- **WHEN** 归一化为 `LLMResponse` / `LLMChunk`
- **THEN** 对应 `finish_reason` 为 `"length"`，其余字段逐字不变

#### Scenario: 非截断取值原样保留

- **GIVEN** `finish_reason` 为 `"stop"` / `"content_filter"` / 未知取值，或字段缺失
- **WHEN** 归一化
- **THEN** 已知非截断取值原样保留；字段缺失时流式为空串、非流式为 `"stop"`（既有口径逐字不变）

### Requirement: 请求侧输出上限按预留注入

统一补全请求 `LLMRequest.max_tokens` SHALL 由组合根按**输出预留**（`loop.output_reserve`）注入：
`LLMPlanner` SHALL 提供构造期注入点，取值 **> 0** 时 SHALL 填入每次请求的 `max_tokens`（provider
据此下发输出上限）；注入点缺省 `None` **或**取值 **≤ 0** 时 SHALL NOT 下发该字段（既有请求形状
逐字不变 —— 端点不支持 / 上限更低时零影响）。

内置默认 provider 在构建请求体时 SHALL 按模型名查询**内置输出能力表**：

- 已知最大输出 **> 0** 且请求上限更大 ⇒ 请求体 SHALL 使用模型上限（**钳制**）；
- 上限字段 SHALL 按能力表选择（`max_tokens` 或 `max_completion_tokens`），SHALL NOT 同时下发
  两个上限字段；
- 表**未收录**或最大输出未知（`0`）⇒ SHALL 逐字保持既有行为（字段 `max_tokens`、原值）。

能力表 SHALL 只收录**有据可查**的常见模型族，SHALL NOT 猜测；表自身 SHALL NOT 新增配置键
（不新增 CLI / env / yaml 面，SHALL NOT 成为第二真源）。显式 `loop.output_reserve` 仍是请求上限的
**首选值**：钳制只会在模型已知上限更低时向下收紧，SHALL NOT 抬高用户配置。

该注入使「预留」从**记账假设**变为**端点上界**：预算派生（`窗口 − 预留`）本已假设输出至多占预留
这么多 token，下发后模型侧不再可能越界产出 ⇒ 记账与实际上界一致。

#### Scenario: 注入正预留即下发输出上限

- **GIVEN** `LLMPlanner` 经构造注入 `max_tokens = 8192`，模型未收录于能力表
- **WHEN** 构建补全请求
- **THEN** 请求 `max_tokens` 为 `8192`，provider 请求体携带 `max_tokens: 8192`

#### Scenario: 未注入或非正预留不下发

- **GIVEN** `LLMPlanner` 未注入 `max_tokens`（缺省），或注入值 `≤ 0`
- **WHEN** 构建补全请求
- **THEN** 请求 `max_tokens` 为 `None`，provider 请求体**不含**任何输出上限键（与既有实现逐字一致）

#### Scenario: 已知模型上限低于预留时钳制

- **GIVEN** 模型 `gpt-4-turbo`（已知最大输出 `4096`），请求上限 `8192`
- **WHEN** provider 构建请求体
- **THEN** 请求体携带 `max_tokens: 4096`，SHALL NOT 携带 `8192`

#### Scenario: 已知模型要求专用上限字段

- **GIVEN** 模型 `o1` 或 `gpt-5`（能力表指定 `max_completion_tokens`），请求上限 `8192`
- **WHEN** provider 构建请求体
- **THEN** 请求体携带 `max_completion_tokens: 8192`，SHALL NOT 携带 `max_tokens` 键

#### Scenario: 未收录模型请求体逐字不变

- **GIVEN** 模型未收录于能力表，请求上限 `8192`
- **WHEN** provider 构建请求体
- **THEN** 请求体携带 `max_tokens: 8192`，字段名与数值均与引入本能力表前逐字一致
