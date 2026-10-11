# Loop Specification Delta — 夹带的动作 JSON 归一为可见失败（change 0222）

## MODIFIED Requirements

### Requirement: 推理动作解析与失败可见

循环 SHALL 把推理输出解析为**终止动作**（空 `tool_id`，本轮进入回复收尾）或**工具动作**
（非空 `tool_id`，交给执行链）。解析 SHALL 覆盖五种形态，且**只认严格形态、不做启发式猜测**：

1. **原生工具调用**（provider 返回的 `tool_calls`）：优先于内容协议，行为与既有实现逐字一致；
2. **纯 JSON 对象**（整段内容即 `{"tool_id": …, "args": …}`）：行为与既有实现逐字一致；
3. **尾部动作 JSON**（内容不以 `{` 开头，但其**尾部**为一个可解析的 JSON 对象、且含非空
   `tool_id`；允许以 Markdown 围栏收尾）：SHALL 按工具动作处理，与形态 2 **同一套语义**
   （参数校验仍由工具调用链承担，本层不另造副本）；
4. **未闭合的动作载荷**（内容不以 `{` 开头、尾部亦无可解析的含 `tool_id` JSON 对象，但
   **尾部存在**一处以 `"tool_id"` 标记起、**到内容结束仍未闭合**的 JSON 结构 —— 即模型确实在
   **发出**动作协议，只是产出被截断或被写坏）：SHALL 以**失败态终止动作**收尾，SHALL NOT
   把该段原文当作最终回复。
5. **夹带的动作 JSON**（内容不以 `{` 开头、**非尾部**处存在一处**已闭合**的可解析 JSON 对象、
   且含非空 `tool_id` —— 即模型确实写出了一个完整动作协议，却又在其后追加了正文）：SHALL 以
   **失败态终止动作**收尾（`LLM_PLAN_PARSE_FAILED`），SHALL NOT 把该段原文当作最终回复、
   SHALL NOT 执行该动作（本层 SHALL NOT 做「JSON 在正文中间该不该执行」的启发式猜测）。

形态 4 的判据 SHALL 为**严格形态**：自**最后一次**出现的 `"tool_id"` 回退至其外层 `{`，做
**字符串感知**的括号深度扫描，深度**从未**回到 0 即命中。**闭合**的尾部对象 —— 不论其后是否
仍有正文、是否含 `tool_id` —— SHALL NOT 命中本形态。

内容不以 `{` 开头、且**尾部无可解析的动作对象、文本中亦无夹带的动作对象**时，整段内容 SHALL
作为**自然语言回复**（终止动作）—— 与既有实现逐字一致。正文中间夹带的**非动作** JSON 对象
（**无** `tool_id` 字段，如示例 / 配置）SHALL NOT 触发动作解析（仍按回复）；正文中间夹带的
**动作** JSON 对象（含非空 `tool_id`）SHALL 归一为**形态 5**。本条 SHALL **取代**既有「正文
中间夹带一律按回复」的语义 —— 旧语义把「完整动作协议 + 尾随正文」整段当答复（记成功、JSON
进转录与记忆的**静默零执行**），其代价高于一次**可见**的解析失败。

推理产出**不可用**（解析失败 `LLM_PLAN_PARSE_FAILED` 各分支、模型调用失败）时，循环 SHALL 以
**失败态终止动作**收尾：该轮 `trajectory` 记 `ok=False`、`loop_finished` 载荷 `failed=true`、
`LoopResult.failed=true`、收尾观察者 SHALL 收到 `ok=False`。该失败态 SHALL NOT 外溢为工具执行
语义 —— 工具动作失败是否影响本轮成败 SHALL NOT 由本条约束（另议）。

失败态终止动作中，「内容以 `{` 开头但无法解析」、**形态 4** 与**形态 5** 三类 SHALL 另带**有界的原始产出**
（`Action.raw_output`，上界由实现定，超出即截断），供呈现层折叠展示与 trace 留痕；该原始产出
SHALL NOT 写入转录 / 记忆 / 笔记，SHALL NOT 并入 `reply`（`reply` SHALL 为**可读提示**）。
**形态 4** 的成因措辞 SHALL 在信号可用时区分：provider 报告 `finish_reason="length"` ⇒ 提示 SHALL
明示**被截断**；信号不可用 ⇒ 提示为**未闭合**（疑似截断或写坏）；二者**失败语义相同**。

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

- **GIVEN** 模型内容不含任何**含非空 `tool_id`** 的 JSON（纯文本、或正文中夹带**无** `tool_id`
  的示例 JSON、或示例对象在文末但**无** `tool_id` 字段、或示例对象在文末但**已闭合**）
- **WHEN** 循环解析该输出
- **THEN** 得到**终止动作**，`reply` 为该段原文，且**不标记**失败
- **AND** 与既有实现逐字一致（零回归）

#### Scenario: 夹带的动作 JSON 归一为可见失败

- **GIVEN** 模型内容为「正文 + 一处**已闭合**的 `{"tool_id": …, "args": {…}}` + 其后的正文」
  （动作 JSON **不在**文末，即尾部对象之外另有可解析的含 `tool_id` 对象）
- **WHEN** 循环解析该输出
- **THEN** 得到**失败态终止动作**，`reply` 为 `LLM_PLAN_PARSE_FAILED` 可读提示且**不含** `"tool_id"`
- **AND** 该动作 **SHALL NOT** 被执行，SHALL NOT 把整段原文当作最终回复
- **AND** `Action.raw_output` 非空有界，本轮 `trajectory` 该步 `ok=False`

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

#### Scenario: 未闭合的动作载荷不再被当作正文

- **GIVEN** 模型内容为「一段解释文字 + 换行 + `{"tool_id": "tools.file_write", "args": {"path":
  "a.md", "content": "一段长正文` 」（外层对象**未闭合**，文本末尾止于内层字符串）
- **WHEN** 循环完成该轮
- **THEN** 得到**失败态终止动作**，`reply` 为可读提示且**不含** `"tool_id"`
- **AND** 本轮 `trajectory` 的该步 `ok=False`、`loop_finished` 载荷 `failed=true`、
  `LoopResult.failed=true`、收尾观察者收到 `ok=False`

#### Scenario: 未闭合载荷的原始产出有界且不进持久面

- **GIVEN** 模型内容命中形态 4（未闭合动作载荷）
- **WHEN** 循环完成该轮
- **THEN** 该终止动作的 `Action.raw_output` 非空且长度不超过实现上界，`LoopResult.raw_output` 与之一致
- **AND** 本轮转录与记忆沉淀 SHALL NOT 含该原始产出（只含可读提示）

#### Scenario: provider 报告截断时提示区分成因

- **GIVEN** 模型内容命中形态 4，且 provider 报告 `finish_reason="length"`
- **WHEN** 循环完成该轮
- **THEN** `reply` 的提示 SHALL 明示「截断」
- **AND** `finish_reason` 不可用（未携带 / 空串）时，提示 SHALL 为「未闭合」措辞，且失败语义
  （`failed=true` / `ok=False`）与前者**相同**
