Core Profile 与上下文工程衔接的增量规格：将 Core.md 的「宪法与全局规则」分区作为 constitution:v1 coeffect 注入上下文并作为必保约束，并将项目级 Core.md 内容作为项目信息注入窗口，对齐 Claude Code / OpenClaw 的灵魂文件机制。

（来源：exploration_findings.md，2026-09-21）

## ADDED Requirements

### Requirement: 宪法约束注入
系统 SHALL 将 Core Profile 的「宪法与全局规则」分区作为 constitution:v1 coeffect 注入上下文，作为必保约束参与执行。

#### Scenario: 宪法分区注入
- **GIVEN** 全局 Core.md 含「宪法与全局规则」分区
- **WHEN** 上下文装配器构建上下文
- **THEN** 该分区内容作为 constitution:v1 coeffect 注入，并作为必保约束保留

### Requirement: 项目信息注入
系统 SHALL 在载入项目时由 ContextEngine 按 cwd 向上查找项目级 Core.md，将其内容作为项目信息注入上下文窗口。

#### Scenario: 项目信息注入
- **GIVEN** 当前工作目录位于某项目内，且项目根存在 Core.md
- **WHEN** ContextEngine 装配项目上下文
- **THEN** 命中的项目级 Core.md 内容注入上下文，作为项目信息参与任务

#### Scenario: 未命中降级
- **GIVEN** 从 cwd 向上至文件系统根均未发现项目级 Core.md
- **WHEN** ContextEngine 查找失败
- **THEN** 静默降级，不注入项目信息，不影响任务执行
