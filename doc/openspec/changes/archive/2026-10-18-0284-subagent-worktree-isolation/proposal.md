# Proposal 0284 — 子 Agent 工作树隔离

## Why

`tools.delegate` 的前台与后台子 Agent 当前与主 Agent **共享同一进程 cwd**：

- 两个子 Agent（或子 Agent 与主 Agent）并行写同一相对路径时，只靠重复调用抑制与操作纪律，
  没有文件系统级隔离；一个任务的半成品会立刻污染另一个任务的输入。
- 子 Agent 结束后没有可复核、可回滚的产物边界：要区分「哪些改动来自哪个子 Agent」只能
  翻可逆效应账目或人工比对工作区。
- 失败恢复只能依赖 `EffectTracker` 的逐操作 undo；工作区级快照/丢弃能力缺失。

对齐报告（`doc/01-architecture/claude-code-alignment.md`）把「子 Agent 工作区隔离」列为
P0 最大结构性缺口。本 change 用 git worktree 补齐该面，并保持缺省关闭以零影响既有委托路径。

## What Changes

1. **git 工作树原语**：`GitBackend` 增加 `repo_root` / `worktree_add` / `worktree_list` /
   `worktree_remove` / `branch_exists` / `delete_branch` 六个**本地**原语；错误仍归一为
   `GitError` 且不回显 stderr；选项式参数拒绝。`GitClient` 的远程/审批面不变。
2. **工作区上下文**：新增 `core.tools.workspace`（仅 stdlib）以 `ContextVar` 承载当前工作区；
   文件工具的相对路径与 `code_run` 的缺省 `cwd` 解析到工作区。绝对路径与 `~` 保持原义，
   **明确不是安全沙箱**。
3. **`WorktreeManager` 与租约**：在 `$CORE_STATE_DIR/worktrees/<repo_key>/<worktree_id>/`
   创建独立工作树（分支 `core-agent/wt-<id>`），sidecar 0600 原子登记；非 git、无提交、
   状态目录位于仓库内均 fail-closed。终态**保留**工作树与分支。
4. **委托接线**：开关 `orchestration.worktree_isolation`（缺省 false）开启后，前台 `_dispatch`
   与后台 `_delegate` 每次委托先创建租约；后台登记、完成通知与跨重启记录携带工作树标识。
5. **清理面**：主工具面新增 `tools.worktree.list`（只读）与 `tools.worktree.discard`
   （HIGH_RISK、需审批、不可逆）；子 Agent 工具面不可见。
6. **顺带修复**：`tools.task_retry` 的同步 handler 经 `asyncio.to_thread` 调 `registry.spawn`，
   后者在工作线程 `asyncio.create_task` 必然抛 `RuntimeError: no running event loop`。
   本 change 把该 handler 改为 `async def`（重入队要创建工作树，必须先修）。

## Impact

- 受影响规格：`orchestration`（ADDED 子 Agent 工作树隔离）、`configuration`（ADDED 工作树隔离
  配置）、`git`（ADDED 工作树与分支原语）、`permission`（ADDED 工作树工具权限口径）。
- 代码：`src/core/git/{backend,subprocess_backend}.py`、新 `src/core/tools/workspace.py`、
  新 `src/core/orchestration/{state_files,worktrees}.py`、`src/core/orchestration/background.py`、
  `src/core/tools/builtin.py`、`src/core/configuration/manager.py`、`src/core/runtime.py`。
- 兼容性：缺省关闭时委托结果、工具面、通知、持久化字段逐字不变；`_PERSIST_VERSION` 保持 1，
  旧登记文件照常加载；不新增三方依赖、不新增模型侧 git 写工具。
- 文档：ADR-0274、known-risk E220、test-cases §196，模块/接口/对齐报告同步更新。

## 不做（边界）

- `TaskScheduler` 波次子任务隔离与跨子任务合并语义（顺序子任务依赖彼此未提交文件）。
- 自动合并、自动提交、自动删除、自动 prune、GC/配额、可配置根/分支前缀/上限。
- 安全沙箱：绝对路径、`~`、符号链接逃逸、网络均不受约束。
- `GitClient` 远程/审批新方法、MCP 暴露、UI/TUI 工作树视图。
- 修复 `file_write` / `file_patch` 跨并发任务共享快照列表的潜在问题（记入 ADR 局限）。
