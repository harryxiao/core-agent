# 接口设计：版本控制（Git Interface）

> 模块：`12-git/git-architecture.md` ｜ 规格：`openspec/specs/git/spec.md`

---

## 1. GitClient 接口（版本控制核心操作）

内核 loop 与调用方只依赖此抽象接口；底层 git 实现收敛于单一适配器，经依赖注入装配，替换实现零改动。

```python
class GitClient:
    def init(self, path: str) -> str:
        """初始化仓库，返回仓库根路径。"""

    def clone(self, url: str, path: str, *, branch: str | None = None) -> str:
        """克隆远程仓库到本地（超时/认证失败/断线重试见 §4），返回仓库根路径。"""

    def commit(self, message: str, *, paths: list[str] | None = None) -> str:
        """提交工作区改动（paths 为空则全量），返回 commit id。"""

    def status(self) -> GitStatus:
        """返回工作区状态（当前分支 / 已改动 / 未跟踪 / 冲突文件）。"""

    def diff(self, *, ref: str | None = None) -> str:
        """返回与 ref（默认 HEAD）的差异；ref 为 None 时返回工作区未暂存差异。"""

    def log(self, *, count: int = 20) -> list[CommitLog]:
        """返回最近 count 条提交记录。"""

    def branch(self, name: str, *, base: str | None = None) -> None:
        """基于 base（默认当前 HEAD）创建分支。"""

    def checkout(self, ref: str) -> None:
        """切换到指定分支 / 提交。"""

    def merge(self, branch: str) -> MergeResult:
        """合并目标分支；冲突时返回 merged=False 并报告冲突点。"""

    def stash(self, *, message: str | None = None) -> None:
        """暂存工作区改动。"""

    def stash_pop(self) -> None:
        """恢复最近一次 stash。"""

    def pull(self, *, remote: str = "origin", branch: str | None = None) -> None:
        """拉取并合并远程分支；冲突 / 超时 / 认证失败 / 断线重试见 §4。"""

    def push(self, *, remote: str = "origin", branch: str | None = None, force: bool = False) -> None:
        """推送本地分支；force=True 属高危操作，经 permission 审批链拦截，不经由本接口静默绕过。"""

    def delete_remote_branch(self, branch: str, *, remote: str = "origin") -> None:
        """删除远程分支；属高危操作，经 permission 审批链拦截，非交互默认拒绝。"""

    def rewrite_history(self, message: str) -> str:
        """改写历史（`--amend` 最近一次提交），返回新 commit id；属高危操作，经审批链拦截。"""
```

> 高危操作（`force=True` 推送、删除远程分支、历史改写）由 permission 审批链拦截；凭据经 keychain 注入，不落盘明文、不进日志（见 `03-interfaces/permission-interface.md`）。
> **三处高危 op id 互异**（change `0138`）：`git.push(force)` / `git.delete_remote_branch` /
> `git.rewrite_history` —— 审批回调可据此区分事由；三者**均在触碰后端前**阻断。
>
> **审批门错误码**（change `0135`）：未获批准的高危操作 **fail-closed** 阻断并抛
> `AccessControlError(APPROVAL_REQUIRED)`（「缺审批」而非「无权限」；此前误用 `PERMISSION_DENIED`）。
> 非交互（无 `approval` 回调）恒视为未批准 ⇒ 默认拒绝，后台子进程若要自动化须显式注入审批回调。

> **远程可靠性（change `0138` / ADR-0131）**：`clone` / `pull` / `push` / `delete_remote_branch`
> 走**可重试**路径（`_run_remote`）：瞬态网络故障按**指数退避**（`backoff * 2**(n-1)`）重试至
> `attempts` 上限（缺省 3 次 / 0.5s 基数），达上限抛归一错误；**认证失败 / 超时 / 冲突 / 非瞬态失败不重试**。
> 本地原语（`commit` / `status` / `merge` …）不重试。

---

## 2. 数据类型

```python
@dataclass
class WorktreeEntry:                 # change 0284
    path: str
    head: str                        # detached 时为 commit id
    branch: str | None               # 去 refs/heads/ 前缀；detached / bare 为 None
    bare: bool
    prunable: bool

@dataclass
class GitStatus:
    branch: str                     # 当前分支
    changed: list[str]              # 已改动文件
    untracked: list[str]            # 未跟踪文件
    conflicted: list[str]           # 冲突文件

@dataclass
class CommitLog:
    commit_id: str
    author: str
    message: str
    ts: str                         # ISO 时间戳

@dataclass
class MergeResult:
    merged: bool                    # 是否无冲突合并成功
    conflict_files: list[str]       # 冲突文件（merged=False 时非空）
```

---

## 3. 依赖注入隔离（MAL）

- 底层 git 实现（subprocess 直调 git CLI / gitpython / dulwich 等）收敛于**单一适配器**，懒 import，异常归一到领域错误码（见 §4），不泄漏底层库异常结构。
- 经依赖注入装配（构造 / registry），内核 loop 与调用方只依赖 `GitClient` 抽象；替换底层实现仅改装配点，调用方零改动。
- **生产缺省后端 = `SubprocessGitBackend`**（`src/core/git/subprocess_backend.py`）：stdlib `subprocess` 直调 `git` CLI，**零第三方依赖**。构造 `SubprocessGitBackend(cwd=None, *, timeout=60.0, attempts=3, backoff=0.5, sleep=None)`；`cwd` 为**仓库根**（缺省 `Path.cwd()`），`init(path)` / `clone(url, path)` 完成后后端把 `cwd` 指向新仓库（等同「一次会话绑定一个仓库」）。`attempts` / `backoff` 控制远程重试上限与退避基数；`sleep` 可注入（缺省 `time.sleep`）⇒ 测试零真实等待。
- `build_backend()` 恒返回该适配器（构造注入者优先）；`GitClient` 因此**开箱可用**，不再有「离线未接」错误。

### 3.1 工作树与分支原语（change `0284` / ADR-0274）

本地操作原语加在 `GitBackend` / `SubprocessGitBackend`，**不加在 `GitClient`**（工作树生命周期
不属远程 / 审批面，由 `WorktreeManager` 直接消费 backend）：

```python
class GitBackend:                    # 新增（Protocol）
    def repo_root(self) -> str: ...                  # rev-parse --show-toplevel，realpath
    def worktree_add(self, path: str, *, branch: str, base: str = "HEAD") -> None: ...
    def worktree_list(self) -> list[WorktreeEntry]: ...
    def worktree_remove(self, path: str, *, force: bool = False) -> None: ...
    def branch_exists(self, name: str) -> bool: ...
    def delete_branch(self, name: str, *, force: bool = False) -> None: ...
```

- **选项注入防护**：`path` / `branch` / `base` / `name` 以 `-` 开头 ⇒ `GitError(GIT_COMMAND_FAILED)`，
  消息**不回显取值**。
- **错误归一**：`worktree remove` 命中 dirty 特征 ⇒ `GIT_WORKTREE_DIRTY`；其余走 `_classify`，
  **永不回显 stderr**。
- **`GitClient` 不变**：既有远程 / 审批面零变化；`build_backend(cwd=None)` 的构造兼容扩展。
- **平台**：`git worktree` 由主机 git CLI 提供；Windows 只覆盖路径与命令面的单元行为。

---

## 4. 错误码

| 错误码 | 含义 |
|---|---|
| `GIT_AUTH_FAILED` | 远程认证失败（凭据过期 / 无权限，不泄露凭据） |
| `GIT_REMOTE_TIMEOUT` | 远程操作超时 |
| `GIT_WORKTREE_DIRTY` | 工作区有未提交改动，操作被拒绝 |
| `GIT_CONFLICT` | 合并 / 拉取冲突，需人工解决 |
| `GIT_COMMAND_FAILED` | git 子命令非零退出（非上述分类），信息为固定提示，**不回显 stderr** |

**可重试分类**（change `0138`）：仅 `GIT_COMMAND_FAILED` **且** stderr 命中瞬态网络特征
（`could not resolve host` / `connection reset` / `connection refused` / `rpc failed` / `early eof` /
`network is unreachable` …）者按指数退避重试；`GIT_AUTH_FAILED`（凭据不会自愈）、`GIT_REMOTE_TIMEOUT`
（spec 要求超时即中止）、`GIT_CONFLICT`（需人工）与确定性 `GIT_COMMAND_FAILED` **一律不重试**。

---

## 5. 关联

- 模块：`12-git/git-architecture.md`
- 规格：`openspec/specs/git/spec.md`
- 审批：`03-interfaces/permission-interface.md`（高危操作审批链）
