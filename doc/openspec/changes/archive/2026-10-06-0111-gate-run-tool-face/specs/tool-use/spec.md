# Tool-Use Specification Delta

## ADDED Requirements

### Requirement: 质量门禁工具
系统 SHALL 把既有的四道质量门禁（lint / typecheck / test / build）暴露为单个原子工具 `tools.gate_run`，使 Agent 可经工具调用通道按**门禁名**触发门禁并取回结构化结果。门禁名集合与门禁命令 SHALL 取自 `ci-cd` 的**单一真源**（`GATE_COMMANDS`），该工具 SHALL NOT 另立一套门禁命令或第二个门禁执行器；门禁执行器 SHALL 经**构造参数注入**（工具层 SHALL NOT 依赖交付流水线层）。该工具 SHALL 诚实声明 `process`/`filesystem` 副作用且为**不可逆**，照旧受确认门约束（高风险需人工审批）；门禁名不在真源内时 SHALL fail-closed 拒绝，SHALL NOT 触达执行器。

#### Scenario: 按名触发门禁
- **GIVEN** Agent 需在改动后自检，且已注入门禁执行器
- **WHEN** 调用 `tools.gate_run` 并给出门禁名（如 `lint`）
- **THEN** 经注入执行器按 `GATE_COMMANDS` 单一真源执行该道门禁，返回结构化结果（门禁名 / 是否通过 / **有界**失败原因）

#### Scenario: 门禁工具不可逆走确认门
- **GIVEN** 未处于无人值守自动放行档
- **WHEN** 执行 `tools.gate_run`
- **THEN** 因声明 `process`/`filesystem` 副作用且不可逆而触发**人工审批**，未批准则结构化拒绝执行（`IRREVERSIBLE_BLOCKED`）

#### Scenario: 未知门禁 fail-closed
- **GIVEN** 门禁名不在单一真源内（如 `deploy`）
- **WHEN** 调用 `tools.gate_run`
- **THEN** 结构化拒绝（`EXECUTION_FAILED`），且**不执行任何命令**、不触达注入的执行器

#### Scenario: 门禁名集合与单一真源一致
- **GIVEN** 组合根装配了该工具
- **WHEN** 读取其 schema 的门禁名枚举
- **THEN** 枚举与 `GATE_COMMANDS` 的键集合**逐字一致**（无第二份门禁名清单）
