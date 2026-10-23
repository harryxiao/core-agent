# Spec Delta — configuration（0307 巩固模式配置）

## ADDED Requirements

### Requirement: 巩固模式配置

系统 SHALL 将知识固化（`MemoryStore.compact`）的开关纳入 ConfigSpec 单一真源：
`memory.consolidation_mode`，取值 `active` / `off`（大小写与首尾空白归一），缺省 `active`。
三面 SHALL 齐备：CLI flag `--memory-consolidation-mode`、环境变量
`CORE_MEMORY_CONSOLIDATION_MODE`、config.yaml `memory.consolidation_mode`。

组合根 SHALL 以 `consolidation_mode() != "off"` 注入 `MemoryStore(consolidation_enabled=...)`。
`memory` 段为非结构化段 ⇒ 集合外取值（含拼写错误）SHALL 归一为 `active`（保持变更前行为，
不阻断启动）。未加载配置时访问器 SHALL 返回 `active`。

#### Scenario: 缺省开启

- **GIVEN** 未配置 `memory.consolidation_mode`
- **WHEN** 组合根构造 `MemoryStore`
- **THEN** `consolidation_enabled=True`（固化行为与变更前逐字一致）

#### Scenario: 三面关闭

- **GIVEN** `memory.consolidation_mode` 经 yaml / CLI flag / 环境变量任一设为 `off`
- **WHEN** 组合根构造 `MemoryStore`
- **THEN** `consolidation_enabled=False`，`compact()` 为 no-op

#### Scenario: 环境变量覆盖 yaml

- **GIVEN** yaml 为 `active`、环境变量为 `off`
- **WHEN** 读取 `consolidation_mode()`
- **THEN** 返回 `off`

#### Scenario: 非法取值归一为开启

- **GIVEN** `memory.consolidation_mode` 取 `disable` / `ong` / 布尔 / 数字
- **WHEN** 读取 `consolidation_mode()`
- **THEN** 返回 `active`，不阻断启动
