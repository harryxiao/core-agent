# configuration — 已知模型能力告警（change 0293）

## ADDED Requirements

### Requirement: 已知模型能力告警

配置校验 SHALL 在内置能力表命中时产生**仅告警、不阻断**的提示：

- `loop.output_reserve` **大于**该模型已知最大输出 ⇒ SHALL 告警，说明请求将按模型上限钳制
  （钳制口径见 llm-provider「请求侧输出上限按预留注入」）；
- `llm.reasoning_effort` 非空且该模型**已知不支持**该字段 ⇒ SHALL 告警，说明仍会照常下发、
  端点若不接受会报错（本 change SHALL NOT 静默丢弃用户显式配置）。

表未收录、或对应能力未知（最大输出 `0` / 支持性 `None`）⇒ SHALL NOT 产生该类告警，既有校验结果
逐字不变。告警 SHALL NOT 回显端点或密钥；SHALL NOT 改变校验通过与否。

#### Scenario: 输出预留高于已知上限仅告警

- **GIVEN** `llm.model = gpt-4-turbo`（已知最大输出 `4096`），`loop.output_reserve` 取缺省 `8192`
- **WHEN** 配置校验
- **THEN** 校验通过（不阻断启动），并产生含 `output_reserve` 与已知模型上限的告警

#### Scenario: 已知不支持的推理档位仅告警

- **GIVEN** `llm.model = gpt-4o`（已知不支持 `reasoning_effort`），`llm.reasoning_effort = low`
- **WHEN** 配置校验
- **THEN** 校验通过，并产生含 `reasoning_effort` 与模型名的告警；配置值不被丢弃

#### Scenario: 未收录模型不产生能力告警

- **GIVEN** `llm.model` 未收录于能力表
- **WHEN** 配置校验
- **THEN** 不产生本要求的告警，既有校验告警集合与通过与否逐字不变
