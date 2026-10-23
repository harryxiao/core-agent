# Spec Delta — configuration（0310 上下文检查点配置）

## ADDED Requirements

### Requirement: 上下文检查点配置

系统 SHALL 将上下文淘汰的情景检查点纳入 ConfigSpec 单一真源：`memory.context_checkpoint`，
缺省 `True`。三面 SHALL 齐备：CLI flag `--memory-context-checkpoint`、环境变量
`CORE_MEMORY_CONTEXT_CHECKPOINT`、config.yaml `memory.context_checkpoint`。

组合根 SHALL 以 `context_checkpoint_enabled()` 注入 `DefaultLoop(context_checkpoint=...)`。
`false` 是 kill-switch（淘汰时零写入，行为回到变更前）。`memory` 段为非结构化段 ⇒ 缺失、
`bool` 与集合外字符串 SHALL 归一为**开启**（笔误不得静默关闭）；显式 `false` / `0` / `no` /
`off` 等集合内取值归一为**关闭**；未加载配置时访问器 SHALL 返回 `True`。

`DefaultLoop` 的直接构造 SHALL 以 `context_checkpoint=False` 为缺省（未注入 ⇒ 逐字不变）；
只有组合根按配置注入。

#### Scenario: 缺省开启

- **GIVEN** 未配置 `memory.context_checkpoint`
- **WHEN** 组合根读取开关并构造循环
- **THEN** 开关为 `True`，淘汰发生时写检查点

#### Scenario: 三面配置

- **GIVEN** `memory.context_checkpoint` 经 yaml / CLI flag / 环境变量任一设为 `false`
- **WHEN** 读取 `context_checkpoint_enabled()`
- **THEN** 返回 `False`，淘汰零写入

#### Scenario: 环境变量覆盖 yaml

- **GIVEN** yaml 为 `true`、环境变量为 `false`
- **WHEN** 读取 `context_checkpoint_enabled()`
- **THEN** 返回 `False`

#### Scenario: 非法取值归一为开启

- **GIVEN** `memory.context_checkpoint` 取 `"abc"` / `2` / `1.5`
- **WHEN** 读取 `context_checkpoint_enabled()`
- **THEN** 返回 `True`，不阻断启动

#### Scenario: 直接构造逐字不变

- **GIVEN** 直接构造 `DefaultLoop` 且未传 `context_checkpoint`
- **WHEN** 处理任意轮次
- **THEN** 不写任何检查点（开关缺省关闭）
