## MODIFIED Requirements

### Requirement: 默认实现与配置归一化
系统 SHALL 提供 OpenAI 兼容 stdlib 默认实现，任意 OpenAI 兼容 API Key + URL 配置即路由到对应端点，无需逐家编写适配代码。
响应归一化 SHALL **保留推理原文（thinking）**：统一响应模型 `LLMResponse` 与流式增量 `LLMChunk` SHALL 各携带 `thinking` 字段（provider 归一化后的推理文本；端点未返回该字段时为空串，SHALL NOT 以缺省值报错）。归一化 SHALL 覆盖**两家既有口径** —— 智谱 GLM 系与 OpenAI 兼容端点在非流式 `message` 与流式 `delta` 上的推理字段（`reasoning_content` / `reasoning`），流式 SHALL 逐 delta 同口径归一。
`thinking` SHALL NOT 掺入 `content`（回复正文与推理原文分属两字段，SHALL NOT 互相拼接），SHALL NOT 改变 `tool_calls` / `usage` / `finish_reason` 的既有解析。

#### Scenario: 任意三方模型接入
- **GIVEN** 用户配置某三方模型的 API Key 与 URL
- **WHEN** 发起模型调用
- **THEN** 系统自动解析并路由到对应 provider 协议，返回归一化结果

#### Scenario: 原生工具调用解析
- **GIVEN** 请求携带工具（tools 字段）且端点以原生 tool_calls 形式返回（而非 system prompt 约定的 content JSON）
- **WHEN** 收到补全响应或流式增量
- **THEN** 系统把 message.tool_calls / delta.tool_calls 片段归一为 ToolCall（流式按 index 累积 name 与 arguments），上层 planner 据此产出工具 Action，content 协议与原生协议并存兼容

#### Scenario: 推理原文归一（流式与非流式同口径）
- **GIVEN** 端点返回推理原文（`reasoning_content` 或 `reasoning`）
- **WHEN** 该字段出现在非流式响应的 `message` 中，或出现在流式增量的 `delta` 中
- **THEN** 归一化后 `LLMResponse.thinking` / `LLMChunk.thinking` 携带该推理文本，且 `content` 逐字不受影响（两者分属两字段、互不拼接）

#### Scenario: 端点未返回推理字段时为空串
- **GIVEN** 端点响应不含任何推理字段（既有行为）
- **WHEN** 归一化该响应或增量
- **THEN** `thinking` 为空串，`content` / `tool_calls` / `usage` / `finish_reason` 的解析与既有实现**逐字一致**（零回归）
