# constraints spec delta — tool-validation-single-source

**把「调用前 schema 校验」的口径写成单一真源**：同一条义务在实现里有**两份逐字节相同**的
实现（`ToolProvider._validate_args` 与 `Validator.validate_input`，含 `_matches_type` 双拷贝），
任何一侧单独演化都会让「工具层拒绝」与「校验中间件拒绝」静默分叉（账本 E14，E1 走查残留）。

## MODIFIED Requirements

### Requirement: 输入输出校验
系统 SHALL 在工具调用前校验输入 schema/coeffect，在调用后把自由文本解析为结构化指令，解析失败绝不带病执行。

- **口径单一真源**：调用前的 schema 校验（必填 / 类型）SHALL 只有一份实现，即
  :class:`Validator`（`validate_input`）。**工具层（`ToolProvider`）SHALL 委托该口径**，
  SHALL NOT 另实现校验副本；同一非法调用经工具层与经校验中间件得到的拒绝口径 SHALL 一致
  （同样的结构化错误信息）。

#### Scenario: 输入校验失败拒绝执行
- **GIVEN** 一个工具调用的参数不满足 schema
- **WHEN** 校验中间件处理该调用
- **THEN** 调用被拒绝并返回结构化错误

#### Scenario: 输出解析失败不执行
- **GIVEN** 模型返回无法解析的自由文本
- **WHEN** 解析中间件处理该输出
- **THEN** 不执行，重试（有限次）或请求模型修正

#### Scenario: 工具层与校验中间件口径一致
- **GIVEN** 一个参数不满足 schema 的工具调用（缺参或错型）
- **WHEN** 分别经工具层的调用前校验与校验中间件的 `validate_input` 判定
- **THEN** 两者以**同一口径**拒绝（同样的结构化错误信息），不存在两套判定
