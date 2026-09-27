Git 让 Core-Agent 默认支持版本控制操作以完美支撑 Coding 编码能力：提供 clone/init/commit/branch/checkout/diff/merge/log/status/pull/push 等核心操作，保护 .git 元数据与工作区完整性，凭据安全不落盘明文，高危操作（强制推送、删除远程分支、历史改写）走 permission 审批链（来源：research_findings.md，2026-09-20）。

## ADDED Requirements

### Requirement: 版本控制核心操作
系统 SHALL 提供 Git 核心操作：clone/init/commit/branch/checkout/diff/merge/log/status/pull/push，覆盖日常编码版本控制全流程。

#### Scenario: 提交变更
- **GIVEN** 工作区有改动
- **WHEN** 执行 commit
- **THEN** 改动被提交到本地仓库并生成 commit 记录

#### Scenario: 分支切换与合并
- **GIVEN** 存在多个分支
- **WHEN** 执行 checkout / merge
- **THEN** 工作区切换到目标分支；分支合并完成，冲突时明确报告冲突点

### Requirement: .git 仓库与工作区保护
系统 SHALL 保护 .git 元数据与工作区完整性：默认拒绝修改 .git 内部文件，防止误删/篡改仓库结构；操作失败时工作区不处于半损坏状态。

#### Scenario: .git 元数据保护
- **GIVEN** 一次试图修改 .git 内部文件的操作
- **WHEN** 操作执行
- **THEN** 默认拒绝并提示风险，经显式确认或审批后才允许

#### Scenario: 操作失败不损坏工作区
- **GIVEN** 一次 Git 操作中途失败
- **WHEN** 操作执行
- **THEN** 工作区回滚到操作前状态，不处于半提交/半合并状态

### Requirement: 凭据安全
系统 SHALL 保证 Git 凭据安全：凭据经 keychain/系统凭据管理器存储，不落盘明文；日志与报错不泄露凭据与私有仓库地址。

#### Scenario: 凭据不落盘明文
- **GIVEN** 一次远程操作需要认证
- **WHEN** 提供凭据
- **THEN** 凭据经 keychain 存储，仓库配置与日志中不出现明文凭据

### Requirement: 与 permission 沙箱协作
系统 SHALL 让高危 Git 操作（强制推送、删除远程分支、历史改写）走 permission 审批链与沙箱约束，非交互默认拒绝。

#### Scenario: 高危操作审批
- **GIVEN** 一次 force-push 或删除远程分支
- **WHEN** 操作请求
- **THEN** 触发 permission 审批，通过后才执行，拒绝则阻断并审计

