Core Profile 与记忆系统衔接的增量规格：将 Core.md 的「人格」分区作为 L0 元策略写入记忆，厘清 L0 语义（元策略既承载宪法约束，也承载人格预设），对齐 Claude Code / OpenClaw 的灵魂文件机制。

（来源：exploration_findings.md，2026-09-21）

## ADDED Requirements

### Requirement: Core Profile 人格注入
系统 SHALL 将 Core Profile 的「人格」分区作为 L0 元策略写入记忆，承载 Agent 的行为特色预设。

#### Scenario: 人格分区写入 L0
- **GIVEN** 全局 Core.md 含「人格」分区
- **WHEN** Agent 启动读取 Core Profile
- **THEN** 该分区内容作为 L0 元策略写入记忆，塑造 Agent 行为特色
