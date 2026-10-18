# Design 0284 — 子 Agent 工作树隔离

## 1. 决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | 工作区用 `ContextVar`，不重构 loop/provider | 三个 profile 的 loop/provider 只构造一次；`asyncio.create_task` 与 `asyncio.to_thread` 都传播 context，隔离按任务生效；不改 `_normalize_action_args`（单次 run 内工作区恒定，改它只会耦合 loop 与 workspace） |
| D2 | 租约在前台 `_dispatch` / 后台 `_delegate` 创建，registry 只接收 `workspace=lease` | registry 不依赖 git/config；`_run` 在 `use_workspace` 内执行，retry 与首次委托同源 |
| D3 | 工作树创建/丢弃**不记** `EffectTracker` 效应 | 「终态保留」是产品决策；若挂 undo，全局回滚会删除用户期望保留的产物。显式 `discard` 才是逆向操作 |
| D4 | 拆两个工具、用点号 id：`tools.worktree.list`（词元 `list` ⇒ READ）与 `tools.worktree.discard`（无读/写词元 ⇒ deny-by-default HIGH_RISK） | `ToolDef.coeffects` 是工具级静态声明，不能按 action 变化；靠既有分级词元，不改 `PolicyEngine`，也不新增长期字面豁免 |
| D5 | 原语加在 `GitBackend`，不加在 `GitClient` | worktree 是本地生命周期操作，不属远程/审批面；manager 直接消费 backend |
| D6 | 配置三面、缺省 false、非法值阻断启动 | 与 `orchestration.auto_resume` 同口径，不静默降级 |
| D7 | sidecar per-worktree（0600、原子写），不做中央登记表 | 无锁合并复杂度；每棵树独立可损坏容忍；跨重启仍可 enumerate |
| D8 | `tools.task_retry` handler 改 `async def` | 修既有 bug：同步 handler 在工作线程调用 `registry.spawn` → `asyncio.create_task` 无运行循环 |

## 2. 布局与不变量

```
$CORE_STATE_DIR/worktrees/
└── <repo_key>/                    # sha256(realpath(repo_root))[:12]
    ├── wt-<12hex>/                # worktree 本体（0700）
    └── wt-<12hex>.json            # sidecar（0600，原子写）
```

- `worktree_id = "wt-" + uuid4().hex[:12]`；branch `core-agent/wt-<12hex>`。
- sidecar 字段：`version / id / repo_root / path / branch / agent_id / created_at`；
  **不含**任务正文、session、reply、错误。
- 工作树基于 `HEAD` 创建：主工作区未提交改动**不进入**子 Agent。
- 终态（done / failed / cancelled / interrupted）一律保留工作树与分支，不自动删除/prune。
- `discard` 的校验顺序：id 正则 → sidecar 存在 → 锁内重读 → 路径必须**精确等于**
  `<root>/<repo_key>/<id>`（realpath 比较）→ 分支必须等于 `core-agent/wt-<id>` → 执行删除。
  任一不符即拒绝，且不触碰磁盘。

## 3. 工作区路径语义

`resolve_path(path)`：

1. `Path(path).expanduser()`；
2. 绝对路径或带 drive 的非绝对路径（Windows `C:foo`）→ 原样返回；
3. 无当前工作区 → 原样返回（既有行为）；
4. 否则 `workspace_root / path`。

不调用 `resolve()` / `abspath()`，保留既有 `~` 与相对路径行为。只影响**相对路径**与
省略 `cwd` 的 `code_run`；绝对路径、`~`、符号链接逃逸与网络均不受约束 —— 这是路径作用域，
不是安全沙箱。

## 4. 后台任务生命周期

```
_delegate
  ├─ profile 匹配
  ├─ ensure_capacity()                    # 超限先失败，不创建 worktree
  ├─ lease = to_thread(create)            # git worktree add + sidecar
  └─ spawn(..., workspace=lease)          # 登记 worktree 元数据，起 asyncio task
        └─ _run: use_workspace(lease.path)
              ├─ await loop.arun(...)
              └─ best-effort changed_files(lease) 写回 info
  └─ spawn 失败 → remove_quiet(lease)
```

`BackgroundTaskInfo.worktree` 为 dict（`repr=False`），仅在非空时进入 `info()` 与落盘记录；
通知行只带 `；工作树：<id>`。`_sanitize_worktree` 白名单校验，坏值降级 `{}`，不影响整条记录加载。

## 5. 错误与安全

- `WorktreeManager.create` 失败统一 `OrchestrationError(WORKTREE_UNAVAILABLE, ...)`：
  非 git 仓库 / 无 HEAD / 状态目录在仓库内 / 目标目录已存在 / git 命令失败。
  消息只含原因与错误码，**不回显 stderr**。
- git 原语拒绝以 `-` 开头的路径、分支、base（防选项注入）。
- 工作树移除遇脏工作区时映射 `GIT_WORKTREE_DIRTY`；`force=false` 时结构化提示改用 `force=true`。
- 跨进程：`tools.worktree.discard` 只能看到**本进程**后台登记中的 running 任务；另一进程中的
  前台委托无法识别。ADR 记录「不要与另一进程的活跃委托竞争删除」。

## 6. 被拒方案

- **per-task ToolProvider / per-task loop**：复制 `DefaultLoop` 装配，破坏「独立 loop、共享
  memory/tracer/gate」设计；ContextVar 已足够。
- **全局 `os.chdir`**：进程级串行化全部并发任务，且不可取消/异常安全。
- **中央 worktree 登记表**：需复用合并写与锁语义，增加损坏面；sidecar 已满足 enumerate。
- **给 `tools.delegate` 挂 undo 自动删工作树**：与「终态保留」冲突；rollback 会删除用户资产。
- **在 `GitClient` 上开 worktree 方法**：把本地生命周期操作混入远程审批面，扩大模型可见写面。

## 7. 已知局限

- 工作树磁盘占用无配额/GC；保留策略要求外部清理或显式 discard。
- `file_write` / `file_patch` 的 `snaps` LIFO 快照列表按工具实例共享；同一 profile 的并发后台
  任务可能交错 push/pop。本 change 不引入该问题，也不修复（子 Agent trace 回滚不是生产路径）。
- Windows 下工作树移除在任一进程 cwd 位于其中时失败；只报结构化错误，不自动重试。
- `os.chmod` 在 Windows 为 best effort。
