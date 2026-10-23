# Spec Delta — configuration（0309 情景保留期配置）

## ADDED Requirements

### Requirement: 情景记忆保留期配置

系统 SHALL 将情景记忆保留期纳入 ConfigSpec 单一真源：`memory.episodic_retention_days`，
缺省 `90`（天）。三面 SHALL 齐备：CLI flag `--memory-episodic-retention-days`、环境变量
`CORE_MEMORY_EPISODIC_RETENTION_DAYS`、config.yaml `memory.episodic_retention_days`。

组合根 SHALL 以 `episodic_retention_days()` 注入 `MemoryStore`；`0` 是唯一的关闭面
（kill-switch：保留期阶段 no-op，`forget()` 恢复变更前行为）。`memory` 段为非结构化段 ⇒
缺失、`bool`、小数、非数值与负数 SHALL 归一为 `90`（方向恒为「保留策略仍生效」，笔误不得
静默关闭）；未加载配置时访问器 SHALL 返回 `90`。

#### Scenario: 缺省 90 天线入

- **GIVEN** 未配置 `memory.episodic_retention_days`
- **WHEN** 组合根构造 `MemoryStore`
- **THEN** `episodic_retention_days == 90`，`forget()` 会墓碑化超过 90 天的 L2 episodic

#### Scenario: 三面配置

- **GIVEN** `memory.episodic_retention_days` 经 yaml / CLI flag / 环境变量任一设为 `30`
- **WHEN** 读取 `episodic_retention_days()`
- **THEN** 返回 `30`

#### Scenario: 环境变量覆盖 yaml

- **GIVEN** yaml 为 `90`、环境变量为 `7`
- **WHEN** 读取 `episodic_retention_days()`
- **THEN** 返回 `7`

#### Scenario: 0 关闭

- **GIVEN** `memory.episodic_retention_days` 为 `0`
- **WHEN** 组合根构造 `MemoryStore` 并调用 `forget()`
- **THEN** 保留期阶段不产生任何墓碑化

#### Scenario: 非法取值归一为 90

- **GIVEN** `memory.episodic_retention_days` 取 `-5` / `true` / `1.5` / `abc`
- **WHEN** 读取 `episodic_retention_days()`
- **THEN** 返回 `90`，不阻断启动
