# pet-mode spec delta — pet-runtime-wiring

## MODIFIED Requirements

### Requirement: Multi-Pet Management
系统 SHALL 支持同时管理多只宠物，每只宠物拥有独立会话、独立人格、独立任务队列，互不干扰、可独立启停。
宠物注册表 SHALL **跨进程存活**：注册、启停后落盘；新进程加载后可见已注册宠物并对其独立启停。

#### Scenario: 多宠物并行调度
- **GIVEN** 已注册多只宠物
- **WHEN** 系统并行调度多只宠物
- **THEN** 每只独立会话与任务队列，A 宠物异常不影响 B 宠物

#### Scenario: 注册表跨进程存活
- **GIVEN** 某进程激活并注册了一只宠物
- **WHEN** 另一进程加载宠物注册表
- **THEN** 已注册宠物可见（`list`），并可对其独立启停（`stop`）

## ADDED Requirements

### Requirement: Pet Session Runtime Wiring
系统 SHALL 经组合根为生产激活的宠物会话注入真实依赖：唤醒用的主 loop、记忆后端、
受限探索工具集、安全边界与通知器。经生产入口激活的宠物 SHALL 因此满足
「Preference Tracking」与「Background Pet Session Lifecycle」需求 —— 偏好落 L2 facts 层，
唤醒经真实 loop 执行（而非 echo 兜底）。

#### Scenario: 生产激活的宠物偏好落 L2
- **GIVEN** 经组合根装配的运行系统
- **WHEN** 生产入口激活一只宠物并观察主人偏好
- **THEN** 偏好以 `MemoryEntry.source=user` 写入运行系统共享的 L2 facts 层

#### Scenario: 生产激活的宠物唤醒走真实 loop
- **GIVEN** 经组合根装配的运行系统
- **WHEN** 生产入口激活的宠物被唤醒
- **THEN** 唤醒复用运行系统的主 loop（非 echo 兜底 loop）执行自治任务
