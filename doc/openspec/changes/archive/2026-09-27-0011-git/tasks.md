# Tasks

> 注：本 Phase 按项目「不锁选型」立场，git 仅落**可注入抽象**（无真实 git 库代码）。
> 下方标注「真实后端未接」的项 = 抽象（GitClient 13 方法 + GitBackend Protocol 注入 seam + 安全守卫）已落地，真实 git 库（subprocess/gitpython/dulwich）留待后续。

## 1. 版本控制闭环（P0）

- [ ] 1.1 本地仓库操作（init/commit/branch/checkout/diff/log/status）—— 真实后端未接：GitClient 方法 + GitBackend Protocol 已落地，真实 git 库未接
- [ ] 1.2 远程协作（clone/pull/push）—— 真实后端未接：方法 + push(force) 审批已落地，真实远程后端未接
- [ ] 1.3 分支合并与冲突报告—— 真实后端未接：MergeResult(merged, conflict_files) + GIT_CONFLICT 已落地，真实合并未接

## 2. 安全与协作（P1）

- [x] 2.1 .git 元数据保护（_guard_git_paths 拒绝 .git/.git/ 路径 → GIT_WORKTREE_DIRTY）；工作区回滚 deferred（无真实后端）
- [x] 2.2 凭据经 keychain 存储、不落盘明文（SecretRef 引用，不读明文、不进日志）
- [x] 2.3 高危操作走 permission 审批链（force-push 走注入 approval，默认拒绝 → AccessControlError）
