# llm-provider 规格 delta：unparsed-action-visible

## ADDED Requirements

### Requirement: 流式增量携带终止原因

流式增量模型 `LLMChunk` SHALL 携带 `finish_reason` 字段（字符串；该增量块未携带该信息时为空串，
SHALL NOT 以缺省值报错）。provider 归一化 SHALL 从流式增量块的 `choices[0].finish_reason` 取值
（OpenAI 兼容端点通常在**末块**携带，取值如 `stop` / `length`），SHALL NOT 因该字段缺失而丢弃该块
或改写其余字段。归一化 SHALL NOT 改变 `content` / `tool_calls` / `thinking` 的既有语义，
亦 SHALL NOT 改变非流式 `LLMResponse.finish_reason` 的既有解析。

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
