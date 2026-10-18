# loop — 空响应的截断成因诊断（change 0292）

## MODIFIED Requirements

### Requirement: 推理动作解析与失败可见

循环 SHALL 把推理输出解析为**终止动作**（空 `tool_id`，本轮进入回复收尾）或**工具动作**
（非空 `tool_id`，交给执行链）。解析 SHALL 覆盖五种形态，且**只认严格形态、不做启发式猜测**：

1. **原生工具调用**（provider 返回的 `tool_calls`）：优先于内容协议，行为与既有实现逐字一致；
2. **纯 JSON 对象**（整段内容即 `{"tool_id": …, "args": …}`；**允许其后跟随退化残渣** ——
   即仅由结构性符号构成的余部（多余闭合符 / 围栏符 / 零散标点 / 空白），**不含**字母、数字、
   CJK 等**词元**字符；残渣是产出退化、非夹带正文）：行为与既有实现逐字一致；
3. **尾部动作 JSON**（内容不以 `{` 开头，但其**尾部**为一个可解析的 JSON 对象、且含非空
   `tool_id`；允许其后跟随**退化残渣** —— 与形态 2 **同一定义**，含以 Markdown 围栏收尾）：
   SHALL 按工具动作处理，与形态 2 **同一套语义**（参数校验仍由工具调用链承担，本层不另造副本）；
4. **未闭合的动作载荷**（内容不以 `{` 开头、尾部亦无可解析的含 `tool_id` JSON 对象，但
   **尾部存在**一处以 `"tool_id"` 标记起、**到内容结束仍未闭合**的 JSON 结构 —— 即模型确实在
   **发出**动作协议，只是产出被截断或被写坏）：SHALL 以**失败态终止动作**收尾，SHALL NOT
   把该段原文当作最终回复。
5. **夹带的动作 JSON**（内容不以 `{` 开头、**非尾部**处存在一处**已闭合**的可解析 JSON 对象、
   且含非空 `tool_id` —— 即模型确实写出了一个完整动作协议，却又在其后追加了**正文**）：SHALL 以
   **失败态终止动作**收尾（`LLM_PLAN_PARSE_FAILED`），SHALL NOT 把该段原文当作最终回复、
   SHALL NOT 执行该动作（本层 SHALL NOT 做「JSON 在正文中间该不该执行」的启发式猜测）。
   本条判据中的「正文」SHALL 限定为**含词元**的余部；其后**仅**为**退化残渣**（不含词元，
   与形态 2 同一定义）时 SHALL NOT 命中本形态 —— 残渣不构成「追加了正文」的证据，据此丢弃一个
   **完整可用**的动作 SHALL NOT 发生（本形态的判据 SHALL 与形态 2 的容残渣判据**同一谓词、朝向相反**）。

形态 4 的判据 SHALL 为**严格形态**：自**最后一次**出现的 `"tool_id"` 回退至其外层 `{`，做
**字符串感知**的括号深度扫描，深度**从未**回到 0 即命中。**闭合**的尾部对象 —— 不论其后是否
仍有正文、是否含 `tool_id` —— SHALL NOT 命中本形态。

内容不以 `{` 开头、且**尾部无可解析的动作对象、文本中亦无夹带的动作对象**时，整段内容 SHALL
作为**自然语言回复**（终止动作）—— 与既有实现逐字一致。正文中间夹带的**非动作** JSON 对象
（**无** `tool_id` 字段，如示例 / 配置）SHALL NOT 触发动作解析（仍按回复）；正文中间夹带的
**动作** JSON 对象（含非空 `tool_id`）SHALL 归一为**形态 5**。本条 SHALL **取代**既有「正文
中间夹带一律按回复」的语义 —— 旧语义把「完整动作协议 + 尾随正文」整段当答复（记成功、JSON
进转录与记忆的**静默零执行**），其代价高于一次**可见**的解析失败。

内容为空（去除首尾空白后为空）SHALL 仍以**失败态终止动作**收尾。provider 报告
`finish_reason="length"` 时，`reply` 的可读提示 SHALL 明示**输出被截断 / 输出预算可能被思考耗尽**
（SHALL NOT 只报「空响应」）；`finish_reason` 不可用（未携带 / 空串 / 非 `length`）时，`reply`
SHALL 维持既有「`LLM_PLAN_PARSE_FAILED: 空响应`」措辞。两种情形的失败语义（`failed=true`、
`ok=False`、零工具执行、无原始产出）SHALL 相同，本条 SHALL NOT 改变非空内容的任何解析分支。

推理产出**不可用**（解析失败 `LLM_PLAN_PARSE_FAILED` 各分支、模型调用失败）时，循环 SHALL 以
**失败态终止动作**收尾：该轮 `trajectory` 记 `ok=False`、`loop_finished` 载荷 `failed=true`、
`LoopResult.failed=true`、收尾观察者 SHALL 收到 `ok=False`。该失败态 SHALL NOT 外溢为工具执行
语义 —— 工具动作失败是否影响本轮成败 SHALL NOT 由本条约束（另议）。

失败态终止动作中，「内容以 `{` 开头但无法解析」、**形态 4** 与**形态 5** 三类 SHALL 另带**有界的原始产出**
（`Action.raw_output`，上界由实现定，超出即截断），供呈现层折叠展示与 trace 留痕；该原始产出
SHALL NOT 写入转录 / 记忆 / 笔记，SHALL NOT 并入 `reply`（`reply` SHALL 为**可读提示**）。
**形态 4** 与「内容以 `{` 开头但无法解析」的成因措辞 SHALL 在判据命中时区分：命中**未闭合载荷**
判据（复用形态 4 的严格判据）⇒ provider 报告 `finish_reason="length"` 时提示 SHALL 明示**被截断**、
信号不可用时提示为**未闭合**（疑似截断或写坏）；命中**夹带**判据（复用形态 5 的判据，含**对象在前、
正文在后**的形态）⇒ 提示 SHALL 明示「动作 JSON 之后仍跟有正文」；皆不命中 ⇒ 通用「无法解析」提示。
三类措辞**失败语义相同**（失败态、有界原始产出、不进持久面均不变），只改提示信息量。

解析失败的**回喂重试** SHALL 受配置门控（`loop.parse_retry`，缺省**关**）：开启时，推理产出不可用
（`LLM_PLAN_PARSE_FAILED` 各分支）且本轮**未外发任何内容增量**的场合，规划器 SHALL 以同一上下文
追加一条**用户角色**的回喂消息后重试推理**恰一次** —— 消息内容为**失败成因**与**输出格式协议重申**
（含「较长内容分多次、每次写一小段」的用法提示），SHALL NOT 携带该轮原始退化产出（守「有界原始
产出不回模型、不进持久面」的既有边界）；重试可解析 ⇒ 按正常结果处理（工具动作或终止回复）；
重试仍不可用 ⇒ 维持本条失败语义（两次模型调用，不第三次重试）。已外发内容增量（自然语言流已
逐段外发）的场合 SHALL NOT 重试（不得让已见内容「回滚」）；配置关闭（缺省）⇒ 请求形状、模型
调用次数与失败语义与既有实现**逐字一致**。

#### Scenario: 空内容且 provider 报告截断时提示预算耗尽

- **GIVEN** 模型输出去除首尾空白后为空，且 provider 报告 `finish_reason="length"`
- **WHEN** 循环解析该输出
- **THEN** 得到失败态终止动作，`reply` 含 `LLM_PLAN_PARSE_FAILED` 且明示「输出被截断 / 输出预算可能被思考耗尽」
- **AND** 本轮不执行任何工具、无原始产出，失败语义与既有空响应分支相同

#### Scenario: 空内容且无截断信号时维持原文案

- **GIVEN** 模型输出去除首尾空白后为空，且 `finish_reason` 缺失、为空串或不为 `length`
- **WHEN** 循环解析该输出
- **THEN** 得到失败态终止动作，`reply` 逐字为 `LLM_PLAN_PARSE_FAILED: 空响应`
- **AND** 失败语义与截断分支相同

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

#### Scenario: 动作 JSON 之后的退化残渣不阻止执行

- **GIVEN** 模型内容为一个**完整**的 `{"tool_id": "tools.file_write", "args": {…}}`，其后**仅**为
  **退化残渣**（产出退化多出的一个 `}`、或围栏符、或零散标点），**不含**任何词元字符
- **WHEN** 循环解析该输出
- **THEN** 得到**工具动作**（`tool_id` / `args` 取自该对象），本轮进入执行
- **AND** SHALL NOT 标记失败、SHALL NOT 记 `raw_output`（未发生解析失败）
- **AND** 与形态 2 / 形态 3 的容残渣判据**同一谓词、朝向相反**（形态 5 要求余部含词元）

#### Scenario: 残渣容错不适用于其后含词元的内容

- **GIVEN** 模型内容为一个**完整**的动作 JSON，其后跟随**含词元**的正文（字母 / 数字 / CJK）
- **WHEN** 循环解析该输出
- **THEN** 得到**失败态终止动作**（形态 5 语义**不变**，`reply` 明示「动作 JSON 之后仍跟有正文」）
- **AND** 该动作 SHALL NOT 被执行；`Action.raw_output` 非空有界

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

#### Scenario: 首字符花括号的未闭合载荷区分成因

- **GIVEN** 模型内容以 `{` 开头、整体无法 `json.loads` 解析，且命中**未闭合载荷**判据
- **WHEN** 循环解析该输出
- **THEN** 得到失败态终止动作：`finish_reason="length"` ⇒ `reply` 明示「被截断」；信号不可用 ⇒
  `reply` 为「未闭合」措辞；二者失败语义相同，`Action.raw_output` 非空有界

#### Scenario: 首字符花括号闭合对象后仍有正文明示成因

- **GIVEN** 模型内容以 `{` 开头、整体无法解析，其中含一处**已闭合**的动作对象、其后仍有正文
- **WHEN** 循环解析该输出
- **THEN** `reply` 明示「动作 JSON 之后仍跟有正文」，失败语义与形态 5 相同

#### Scenario: 首字符花括号皆不命中判据时维持通用文案

- **GIVEN** 模型内容以 `{` 开头、整体无法解析，且既无未闭合动作载荷、亦无夹带的动作对象
- **WHEN** 循环解析该输出
- **THEN** `reply` 为通用「无法解析模型输出为动作」提示（逐字），失败语义不变

#### Scenario: 解析失败回喂重试恰一次

- **GIVEN** `loop.parse_retry` 已开启，模型首次输出不可解析，且本轮未外发任何内容增量
- **WHEN** 该轮推理执行
- **THEN** 规划器以同一上下文追加一条**用户角色**回喂消息重试**恰一次**：消息含失败成因与输出
  格式协议重申、**不含**原始退化产出；重试可解析 ⇒ 按正常结果处理（本轮不因首次失败而失败）

#### Scenario: 重试仍失败恰两次模型调用

- **GIVEN** `loop.parse_retry` 已开启，模型两次输出均不可解析
- **WHEN** 该轮推理执行
- **THEN** 本轮以失败态终止动作收尾（`reply` 为 `LLM_PLAN_PARSE_FAILED` 可读提示），模型调用
  **恰两次**、不发起第三次重试

#### Scenario: 已外发流式内容不重试

- **GIVEN** `loop.parse_retry` 已开启，流式推理已判定为自然语言回复并**逐段外发**了内容增量，
  最终整段无法解析为动作
- **WHEN** 该轮推理执行
- **THEN** 不重试（模型调用恰一次），维持既有失败语义

#### Scenario: 缺省关闭零重试

- **GIVEN** `loop.parse_retry` 未开启（缺省）
- **WHEN** 模型输出不可解析
- **THEN** 模型调用恰一次、请求不含回喂消息，请求形状与失败语义与既有实现**逐字一致**

