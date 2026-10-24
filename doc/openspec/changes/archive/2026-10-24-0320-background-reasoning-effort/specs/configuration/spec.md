# Spec Delta — configuration（0320 后台派生调用的推理档位透传）

## ADDED Requirements

### Requirement: 后台派生调用的推理档位透传

组合根 SHALL 让**后台派生模型调用**（`_llm_text` 接缝：会话摘要、关键事实 / 关系 / 情景归纳、
SOP 提炼、沉淀候选蒸馏、进化 review / patch author）在构造请求时携带配置的
`llm.reasoning_effort`，与用户交互调用（规划 / 校验 / 流式回复）**同源同值**。

`llm.reasoning_effort` 未配置（空 / 缺省 `None`）时，后台派生请求 SHALL NOT 下发该字段
（请求与引入前逐字一致；端点不支持该字段时零影响）。

该透传 SHALL NOT 引入新的配置键，SHALL NOT 改变主 provider 与后台 provider 的超时 / 重试语义，
SHALL NOT 为后台调用引入 `max_tokens` 缺省上限。

#### Scenario: 配置档位时后台请求携带同值

- **GIVEN** `llm.reasoning_effort` 配置为 `low`
- **WHEN** 轮内压实经 `_llm_text` 发起会话摘要与关键事实抽取调用
- **THEN** 每个后台请求的 `reasoning_effort` 均为 `low`（与用户交互调用一致）

#### Scenario: 未配置档位时不下发

- **GIVEN** 未配置 `llm.reasoning_effort`
- **WHEN** `_llm_text` 发起后台调用
- **THEN** 请求的 `reasoning_effort` 为 `None`，端点请求体不含该字段，行为与引入前逐字一致
