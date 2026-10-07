# loop 规格 delta：loop-output-protocol-tolerance

## ADDED Requirements

### Requirement: 推理动作解析与失败可见

循环 SHALL 把推理输出解析为**终止动作**（空 `tool_id`，本轮进入回复收尾）或**工具动作**
（非空 `tool_id`，交给执行链）。解析 SHALL 覆盖三种形态，且**只认严格形态、不做启发式猜测**：

1. **原生工具调用**（provider 返回的 `tool_calls`）：优先于内容协议，行为与既有实现逐字一致；
2. **纯 JSON 对象**（整段内容即 `{"tool_id": …, "args": …}`）：行为与既有实现逐字一致；
3. **尾部动作 JSON**（内容不以 `{` 开头，但其**尾部**为一个可解析的 JSON 对象、且含非空
   `tool_id`；允许以 Markdown 围栏收尾）：SHALL 按工具动作处理，与形态 2 **同一套语义**
   （参数校验仍由工具调用链承担，本层不另造副本）。

内容不以 `{` 开头、且**尾部无含 `tool_id` 的 JSON 对象**时，整段内容 SHALL 作为**自然语言回复**
（终止动作）—— 与既有实现逐字一致。正文**中间**夹带的 JSON 对象 SHALL NOT 触发动作解析
（已知局限：仅认尾部形态）。

推理产出**不可用**（解析失败 `LLM_PLAN_PARSE_FAILED` 各分支、模型调用失败）时，循环 SHALL 以
**失败态终止动作**收尾：该轮 `trajectory` 记 `ok=False`、`loop_finished` 载荷 `failed=true`、
`LoopResult.failed=true`、收尾观察者 SHALL 收到 `ok=False`。该失败态 SHALL NOT 外溢为工具执行
语义 —— 工具动作失败是否影响本轮成败 SHALL NOT 由本条约束（另议）。

#### Scenario: 混写正文的动作 JSON 被识别为工具调用

- **GIVEN** 模型内容为「一段解释文字 + 换行 + `{"tool_id": "tools.code_run", "args": {…}}`」
- **WHEN** 循环解析该输出
- **THEN** 得到**工具动作**（`tool_id` 为该 JSON 的 `tool_id`、`args` 为其 `args`），本轮进入执行
- **AND** SHALL NOT 把整段文字当作最终回复

#### Scenario: 围栏包裹的尾部动作 JSON 被识别

- **GIVEN** 模型内容为解释文字 + ```` ```json ```` 围栏包裹的 `{"tool_id": …, "args": …}`
- **WHEN** 循环解析该输出
- **THEN** 同样得到**工具动作**

#### Scenario: 非动作 JSON 的自然语言回复不被误判

- **GIVEN** 模型内容不含尾部 `tool_id` JSON（纯文本、或正文中夹带示例 JSON、或示例对象在文末
  但**无** `tool_id` 字段）
- **WHEN** 循环解析该输出
- **THEN** 得到**终止动作**，`reply` 为该段原文，且**不标记**失败
- **AND** 与既有实现逐字一致（零回归）

#### Scenario: 解析失败使本轮失败

- **GIVEN** 模型内容无法解析为动作（如 `{"tool_id": "tools.echo",` 截断的 JSON）
- **WHEN** 循环完成该轮
- **THEN** 本轮 `trajectory` 的该步 `ok=False`
- **AND** `loop_finished` 载荷 `failed=true` 且 `LoopResult.failed=true`
- **AND** 收尾观察者收到的成败为 `ok=False`

#### Scenario: 纯 JSON 与原生工具调用路径零回归

- **GIVEN** 模型输出为纯 JSON 对象、或 provider 返回原生 `tool_calls`
- **WHEN** 循环解析该输出
- **THEN** 解析结果与既有实现**逐字一致**（含缺 `tool_id`/`reply` 时的 `LLM_PLAN_PARSE_FAILED` 文案）
