## ADDED Requirements

### Requirement: 子 Agent 工作树隔离

配置 `orchestration.worktree_isolation` 为 false（缺省）时，委托路径 SHALL 与引入前逐字一致：
不创建工作树、不改变工具面、结果形状、完成通知与持久化字段。开启时，每次 `tools.delegate`
（前台与后台）SHALL 在宿主仓库的独立 git worktree 中运行，分支 SHALL 为
`core-agent/wt-<id>`，路径 SHALL 位于状态目录的 `worktrees/<repo_key>/<worktree_id>/` 下。

工作树 SHALL 基于仓库 `HEAD` 创建；主工作区未提交的改动 SHALL NOT 进入子 Agent 工作树。
子 Agent 使用 `tools.file_read` / `tools.file_write` / `tools.file_patch` 的**相对路径**时，
SHALL 解析到工作树根；`tools.code_run` 省略 `cwd` 时 SHALL 以工作树根为工作目录，显式相对
`cwd` SHALL 相对工作树根解析。绝对路径、`~` 展开结果与符号链接目标 SHALL 保持原语义 ——
本隔离是路径作用域，SHALL NOT 被表述或实现为安全沙箱。

创建 SHALL 在子 Agent 开始前完成，并在以下任一情况 fail-closed 返回结构化错误码
`WORKTREE_UNAVAILABLE`，SHALL NOT 回退到主工作区运行：当前目录不是 git 仓库；仓库没有可
解析的 `HEAD`；状态目录位于仓库内；目标工作树目录已存在；git 命令失败。错误信息 SHALL NOT
回显 git stderr。

任务进入终态（`done / failed / cancelled / interrupted`）后，工作树与分支 SHALL 保留；
系统 SHALL NOT 自动合并、自动提交、自动删除或自动 prune。前台委托结果与后台任务登记 SHALL
携带工作树元数据（`id / path / branch / repo_root / changed_files`），后台完成通知 SHALL 携带
工作树 id（不携带路径）；元数据 SHALL 跨重启保留并可由 `tools.tasks` 查询。

系统 SHALL 在主工具面提供两个工作树工具，子 Agent 工具面 SHALL NOT 包含它们：

- `tools.worktree.list`：只读清单，判 `READ`，coeffect `worktree:read`；返回工作树 id、
  分支、路径、仓库根、agent 与存在性，最多 50 条并报告是否截断（不触发 git 扫描）。
- `tools.worktree.discard`：按 `worktree_id` 显式丢弃，判 `HIGH_RISK`（需人工审批），
  coeffect `worktree:write`，不可逆；SHALL 拒绝正在运行的后台任务所占用的工作树；SHALL
  拒绝登记被篡改、路径越出状态根或分支名不符的记录；`force=false` 时 SHALL 拒绝含未提交
  改动的工作树并提示改用 `force=true`；对不存在或已丢弃的 id SHALL 幂等返回成功且不报错。

工作树 sidecar 登记 SHALL 为 `0600` 原子写，字段 SHALL 限于
`version / id / repo_root / path / branch / agent_id / created_at`，SHALL NOT 包含任务正文、
会话标识或回复内容。状态目录与工作树根 SHALL 为 `0700`（平台不支持时尽力而为）。

#### Scenario: 开关关闭时行为不变

- **GIVEN** `orchestration.worktree_isolation` 未配置或为 false
- **WHEN** 执行前台或后台 `tools.delegate`
- **THEN** 不创建工作树，不注册工作树工具
- **AND THEN** 前台结果仍为 `{ok, reply}`，后台结果仍为 `{ok, task_id, status, agent}`，
  通知与登记文件不新增字段

#### Scenario: 前台子 Agent 的文件写入被隔离

- **GIVEN** 隔离已开启，主仓库位于某个 git 仓库
- **WHEN** 前台子 Agent 以相对路径写入文件
- **THEN** 文件 SHALL 只出现在该子 Agent 的工作树中，主工作区 `git status` SHALL 保持干净
- **AND THEN** 前台结果 SHALL 含工作树 id、路径、分支与非空 `changed_files`

#### Scenario: code_run 缺省工作目录为工作树

- **GIVEN** 隔离已开启
- **WHEN** 子 Agent 执行省略 `cwd` 的 `tools.code_run`
- **THEN** 命令的工作目录 SHALL 为该子 Agent 的工作树根
- **AND THEN** 显式相对 `cwd` 亦 SHALL 相对工作树根解析

#### Scenario: 绝对路径不受工作区约束

- **GIVEN** 隔离已开启
- **WHEN** 子 Agent 使用绝对路径写入主工作区中的文件
- **THEN** 写入 SHALL 落在该绝对路径（主工作区文件被修改）
- **AND THEN** 系统 SHALL NOT 将其重映射到工作树（隔离不是安全沙箱）

#### Scenario: 非 git 仓库 fail-closed

- **GIVEN** 隔离已开启且当前目录不是 git 仓库（或仓库无提交）
- **WHEN** 执行 `tools.delegate`
- **THEN** 委托 SHALL 返回 `ok=false` 与 `WORKTREE_UNAVAILABLE`
- **AND THEN** 子 Agent SHALL NOT 被调用，SHALL NOT 创建任何工作树或 sidecar

#### Scenario: 后台任务隔离且可跨重启查询

- **GIVEN** 隔离已开启
- **WHEN** 后台子 Agent 以相对路径写入文件
- **THEN** 文件 SHALL 落在其工作树，主工作区不变
- **AND THEN** `tools.tasks` SHALL 显示工作树 id/path/branch，完成通知 SHALL 含工作树 id；
  新进程加载登记后 SHALL 仍能查询该元数据

#### Scenario: 终态保留与重入队新工作树

- **GIVEN** 一个后台任务已进入终态（done / failed / cancelled）
- **WHEN** 检查工作树并对其调用 `tools.task_retry`
- **THEN** 原工作树、分支与 sidecar SHALL 保留
- **AND THEN** 重入队 SHALL 创建新的工作树与分支，旧工作树 SHALL NOT 被复用或删除

#### Scenario: 显式丢弃

- **GIVEN** 一个已保留的工作树
- **WHEN** 调用 `tools.worktree.discard`
- **THEN** 工作树目录、分支与 sidecar SHALL 被删除
- **AND THEN** 对同一 id 再次调用 SHALL 幂等返回成功且不报错

#### Scenario: 拒绝运行中任务与越界登记

- **GIVEN** 工作树被一个 running 后台任务占用，或 sidecar 的路径/分支被篡改
- **WHEN** 调用 `tools.worktree.discard`
- **THEN** SHALL 返回 `ok=false` 且不删除任何工作树或外部路径
- **AND THEN** 未提供 `force=true` 时，含未提交改动的工作树亦 SHALL 被拒绝

#### Scenario: 子 Agent 工具面不可见

- **GIVEN** 隔离已开启
- **WHEN** 检查各子 Agent 的工具面
- **THEN** SHALL NOT 含 `tools.worktree.list` 或 `tools.worktree.discard`
- **AND THEN** 两个工具 SHALL 仅在主工具面注册
