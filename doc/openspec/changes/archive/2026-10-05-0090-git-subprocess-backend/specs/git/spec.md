# Git Specification Delta

## MODIFIED Requirements

### Requirement: GitClient 抽象接口与依赖注入隔离
系统 SHALL 通过统一 GitClient 抽象接口提供版本控制操作，内核 loop 与调用方只依赖该接口、不感知具体 git 实现；底层 git 实现（subprocess 直调 git CLI、gitpython、dulwich 等）经依赖注入隔离，替换实现时调用方零改动。生产**缺省**后端 SHALL 为零第三方依赖的 **stdlib `subprocess` 直调 git CLI** 适配器（`SubprocessGitBackend`）；底层子命令以非零码失败时 SHALL 归一到领域错误码（认证失败 / 超时 / 冲突 / 通用命令失败），SHALL NOT 泄漏底层异常结构、凭据或含凭据的远程地址。

#### Scenario: 替换底层 git 实现
- **GIVEN** 需要替换底层 git 实现（如 git CLI → gitpython 库）
- **WHEN** 注册新的 GitClient 实现
- **THEN** 内核 loop 及所有调用方无需改动即可切换

#### Scenario: 缺省后端为零依赖的 subprocess 适配器
- **GIVEN** 未注入任何后端的 GitClient
- **WHEN** 经缺省工厂取得后端
- **THEN** 得到 stdlib `subprocess` 直调 git CLI 的实现（零第三方依赖），可对**真实仓库**完成 init/commit/status/log/diff/branch/checkout/merge/stash 等操作

#### Scenario: 子命令失败归一为领域错误码
- **GIVEN** 一次 git 子命令以非零码失败（认证失败 / 超时 / 冲突 / 其他）
- **WHEN** 适配器处理结果
- **THEN** 抛出携带**领域错误码**的结构化 `GitError`，且错误信息**不回显**原始 stderr（可能含凭据或私有仓库地址）
