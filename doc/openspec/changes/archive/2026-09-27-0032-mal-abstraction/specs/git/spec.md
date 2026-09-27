GitClient 抽象接口与依赖注入隔离：内核只依赖统一 GitClient 抽象、不感知具体 git 实现，底层 git 实现经依赖注入隔离可替换；版本控制核心操作补 stash。（来源：架构审计 MAL 约定，2026-09-27）

## ADDED Requirements

### Requirement: GitClient 抽象接口与依赖注入隔离
系统 SHALL 通过统一 GitClient 抽象接口提供版本控制操作，内核 loop 与调用方只依赖该接口、不感知具体 git 实现；底层 git 实现（subprocess 直调 git CLI、gitpython、dulwich 等）经依赖注入隔离，替换实现时调用方零改动。

#### Scenario: 替换底层 git 实现
- **GIVEN** 需要替换底层 git 实现（如 git CLI → gitpython 库）
- **WHEN** 注册新的 GitClient 实现
- **THEN** 内核 loop 及所有调用方无需改动即可切换

## MODIFIED Requirements

### Requirement: 版本控制核心操作
系统 SHALL 提供 Git 核心操作：clone/init/commit/branch/checkout/diff/merge/log/status/stash/pull/push，覆盖日常编码版本控制全流程。

#### Scenario: 提交变更
- **GIVEN** 工作区有改动
- **WHEN** 执行 commit
- **THEN** 改动被提交到本地仓库并生成 commit 记录

#### Scenario: 分支切换与合并
- **GIVEN** 存在多个分支
- **WHEN** 执行 checkout / merge
- **THEN** 工作区切换到目标分支；分支合并完成，冲突时明确报告冲突点
