# Durability Specification Delta — 保留策略接线（change 0208）

## MODIFIED Requirements

### Requirement: 生命周期与保留策略
系统 SHALL 支持检查点生命周期管理：按保留策略（retention policy，数量上限/时间窗口/存储配额）自动清理过期检查点，避免无限增长；被标记的关键检查点（pinned）不受自动清理影响。

生产接线 SHALL 在检查点**持久化之后**按保留策略自动清理：本接线面暴露**数量上限**（`durability.retention.max_count`，≥1 的整数）与**时间窗口**（`durability.retention.time_window_s`，≥0 的数值）两个配置项；**两者皆未配置时 SHALL NOT 清理任何检查点**（缺省关 ⇒ 既有行为逐字不变）。存储配额通道为**保留库能力**（接口齐备），本次**不接入**生产配置面。自动清理 SHALL 只清理**未 pinned** 的检查点；pinned 检查点 SHALL 不受影响（含数量上限与时间窗口两通道）。非法配置取值 SHALL **阻断启动**（静默兜底会把配置错误变成运行时的诡异行为）。

#### Scenario: 保留策略自动清理
- **GIVEN** 检查点数量或存储达到保留策略上限
- **WHEN** 触发清理
- **THEN** 按策略（时间窗口或 LRU）清理过期检查点并释放存储，保留窗口内的检查点

#### Scenario: 关键检查点保护
- **GIVEN** 某检查点被标记为关键（pinned）
- **WHEN** 自动清理执行
- **THEN** 该检查点不被清理，直到显式取消标记

#### Scenario: 数量上限生效时清理最旧
- **GIVEN** 配置了数量上限 `max_count` 且未 pinned 的检查点数量超过该上限
- **WHEN** 一次检查点持久化触发自动清理
- **THEN** 按时间序清理最旧的未 pinned 检查点，未 pinned 检查点数量回落至上限，最新检查点保留

#### Scenario: 时间窗口生效时清理过期
- **GIVEN** 配置了时间窗口且存在早于（当前时间 − 窗口）的未 pinned 检查点
- **WHEN** 一次检查点持久化触发自动清理
- **THEN** 清理所有过期的未 pinned 检查点，窗口内的检查点保留

#### Scenario: 缺省未配置时不清理
- **GIVEN** 数量上限与时间窗口均未配置
- **WHEN** 检查点反复持久化
- **THEN** 不清理任何检查点（缺省关 ⇒ 既有行为逐字不变）
