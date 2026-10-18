# Tasks 0284 — 子 Agent 工作树隔离

> 验证目标：缺省关闭时委托行为逐字不变；开启后前台/后台子 Agent 的相对路径与 `code_run`
> 落在独立工作树；终态保留、显式丢弃可逆；非 git / 无提交 / 状态目录在仓库内 fail-closed；
> 后台登记、通知、跨重启与 retry 携带工作树；四门禁与 `openspec validate --all` 全绿。

## 1. 规格与测试先行

- [x] 1.1 spec delta：orchestration / configuration / git / permission 四条 ADDED。
- [x] 1.2 新 `tests/test_worktree_backend.py`、`tests/test_worktree_isolation.py`（先红）。

## 2. git 原语

- [x] 2.1 `WorktreeEntry` + `GitBackend` 六原语；`build_backend(cwd=None)`。
- [x] 2.2 `SubprocessGitBackend` 实现（选项注入拒绝、porcelain 解析、dirty 映射、stderr 不回显）。
- [x] 2.3 `core/git/__init__.py` 导出；协议 docstring 更新。

## 3. 工作区上下文

- [x] 3.1 新 `src/core/tools/workspace.py`（`use_workspace` / `workspace_root` / `resolve_path`）。
- [x] 3.2 `builtin._expand` 与 `code_run` cwd 接入；绝对路径/`~` 原语义。

## 4. 状态文件与 WorktreeManager

- [x] 4.1 `orchestration/state_files.py`（搬 lock + 原子 JSON 写），`background._save` 复用。
- [x] 4.2 `errors.py` 增 `WORKTREE_UNAVAILABLE`。
- [x] 4.3 `orchestration/worktrees.py`：lease / create / list / discard / remove_quiet /
      changed_files / 两个工具；sidecar 0600、布局与越界校验。
- [x] 4.4 `orchestration/__init__.py` 导出。

## 5. 后台与运行时接线

- [x] 5.1 `BackgroundTaskInfo.worktree` + `_RECORD_FIELDS` / `_info_record` / `_sanitize_worktree`
      / `_restore_info` / 通知行；`_PERSIST_VERSION` 不变。
- [x] 5.2 `ensure_capacity()`；`spawn(..., workspace=)`；`_run` 工作区与 changed_files。
- [x] 5.3 `task_retry_tool` 改 async + 工作树；修复既有 `no running event loop`。
- [x] 5.4 配置常量 / ConfigSpec / 访问器 / 校验。
- [x] 5.5 runtime：`_worktree_root()`、manager 构造、coeffect、`Runtime.worktrees`、
      前台 `_dispatch`、后台 `_delegate`、工具注册。

## 6. 验证与收尾

- [x] 6.1 四门禁（ruff check / ruff format --check / pyright / pytest）。
- [x] 6.2 反证 3/3（cp 复原 + md5sum）。
- [x] 6.3 `openspec validate --all` 31/0 后归档。
- [x] 6.4 ADR-0274、known-risk E220、test-cases §196、模块/接口/对齐报告。
- [x] 6.5 单次提交 `feat(orchestration): ...` + Co-Authored-By。
