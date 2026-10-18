## ADDED Requirements

### Requirement: 工作树与分支原语

系统 SHALL 在 git 后端抽象（`GitBackend`）上提供以下**本地**原语，供内部工作树管理器使用：
`repo_root()`（解析仓库根）、`worktree_add(path, *, branch, base="HEAD")`、
`worktree_list()`（解析 porcelain，返回路径 / HEAD / 分支，detached 时分支为空）、
`worktree_remove(path, *, force)`、`branch_exists(name)`、`delete_branch(name, *, force)`。
这些原语 SHALL NOT 扩展 `GitClient` 的远程/审批公开面，SHALL NOT 直接编辑 `.git` 内部文件。

原语 SHALL 拒绝以 `-` 开头的路径、分支名与 base（防选项注入）。子命令非零退出 SHALL 归一为
结构化 `GitError`，SHALL NOT 回显原始 stderr、凭据或私有仓库地址。移除含未提交/未跟踪改动的
工作树时，可识别的 dirty 失败 SHALL 映射为 `GIT_WORKTREE_DIRTY`；其余失败 SHALL 按既有
`_classify` 归一。在无提交的仓库上创建工作树 SHALL 结构化失败，SHALL NOT 创建半成品目录。

#### Scenario: 工作树增删查往返

- **GIVEN** 一个至少有一次提交的临时仓库
- **WHEN** 创建带新分支的工作树、列出工作树、再移除它并删除分支
- **THEN** 工作树目录先出现后被移除，`worktree_list()` 曾包含该路径与分支
- **AND THEN** `branch_exists()` 在删除前为 true、删除后为 false

#### Scenario: 无提交仓库创建失败

- **GIVEN** 一个已 `git init` 但尚无提交的仓库
- **WHEN** 创建工作树
- **THEN** SHALL 抛出携带领域错误码的 `GitError`，消息不含 stderr
- **AND THEN** SHALL NOT 留下部分创建的工作树目录或分支

#### Scenario: 脏工作树移除需显式强制

- **GIVEN** 一个含未提交改动的工作树
- **WHEN** 以 `force=false` 移除
- **THEN** SHALL 抛出 `GIT_WORKTREE_DIRTY`
- **AND THEN** 以 `force=true` 移除 SHALL 成功

#### Scenario: 选项式输入被拒绝

- **GIVEN** 路径或分支名以 `-` 开头
- **WHEN** 调用任一工作树原语
- **THEN** SHALL 在调用 git 前拒绝并抛出结构化错误
