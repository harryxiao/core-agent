# Spec Delta — evolution（0305 结晶 / 溶解钩子）

## ADDED Requirements

### Requirement: 架构级候选的结晶产物随结局返回

`EvolutionEngine` 在架构级候选（`kind="plugin"`）的结晶分支调用记忆层钩子
`Crystallizer.crystallize` 时 SHALL NOT 丢弃其返回值：产出 SHALL 随
`EvolutionOutcome.artifact` 返回（该字段缺省为 `None`，对既有构造与结局零影响）。
钩子调用 SHALL 以 `force=True` 进行——该分支此前已强制人工 `confirm`（高风险候选还须匹配的
已批准审批单），属于「显式用户要求」豁免。结局 `status` SHALL 保持 `accepted`（「已批准、待人工
实施」），SHALL NOT 因产物可见而改报 `published` 或改变 `crystallize` 的返回值语义。

未装配记忆层结晶器时，`artifact` SHALL 为 `None`，其余结局字段逐字不变。产物随结局返回后，
其落盘 / 交验证仍由调用方或独立操作面决定；引擎 SHALL NOT 自行把候选写入技能库或记忆。

#### Scenario: 产物随 accepted 结局返回

- **GIVEN** 一个已确认、过门、留出评测不退化、已装配记忆层结晶器的 `kind="plugin"` 候选
- **WHEN** 调用 `crystallize`
- **THEN** 结局 `status == "accepted"`，`artifact` 非空且其 `source_entry_id` 指向本次钩子输入条目

#### Scenario: 未装配钩子时产物为空

- **GIVEN** 同一候选但引擎未装配记忆层结晶器
- **WHEN** 调用 `crystallize`
- **THEN** 结局 `status == "accepted"`，`artifact is None`（其余字段不变）
