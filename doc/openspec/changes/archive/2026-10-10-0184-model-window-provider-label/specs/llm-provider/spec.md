# llm-provider Specification Delta — 已知模型窗口表与 provider 审计标签（change 0184）

## MODIFIED Requirements

### Requirement: 模型调用审计
系统 SHALL 对模型调用做可观测审计，标注 provider / model 与调用结果，复用既有 observability 链路。
`LLMResponse.provider` SHALL 反映**实际使用的 provider 标识**：实现 SHALL 接受构造期注入的
provider 名（组合根按 `llm.provider` 注入），并 SHALL NOT 硬编码字面量；注入值为空（未提供）时
SHALL 回落实现自身的身份标识（`"stdlib"`）。这样「审计标签」与配置面所见一致，不再是与
`llm.provider` 无关的常量。

#### Scenario: 调用留痕
- **GIVEN** 任意一次模型调用
- **WHEN** 调用结束
- **THEN** 审计记录标注 provider / model 与结果，可追溯

#### Scenario: 审计标签反映配置的 provider
- **GIVEN** 组合根按 `llm.provider: litellm` 构造 stdlib 实现
- **WHEN** 该实现完成一次补全
- **THEN** `LLMResponse.provider` 为 `"litellm"`（配置面所见即响应面所见）；未注入 provider 时
  仍为 `"stdlib"`（与既有行为**逐字一致**）
