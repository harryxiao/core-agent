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
```

> 高危操作（`force=True` 推送、删除远程分支、历史改写）由 permission 审批链拦截；凭据经 keychain 注入，不落盘明文、不进日志（见 `03-interfaces/permission-interface.md`）。

---

## 2. 数据类型

```python
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
- **生产缺省后端 = `SubprocessGitBackend`**（`src/core/git/subprocess_backend.py`）：stdlib `subprocess` 直调 `git` CLI，**零第三方依赖**。构造 `SubprocessGitBackend(cwd=None, *, timeout=60.0)`；`cwd` 为**仓库根**（缺省 `Path.cwd()`），`init(path)` / `clone(url, path)` 完成后后端把 `cwd` 指向新仓库（等同「一次会话绑定一个仓库」）。
- `build_backend()` 恒返回该适配器（构造注入者优先）；`GitClient` 因此**开箱可用**，不再有「离线未接」错误。

---

## 4. 错误码

| 错误码 | 含义 |
|---|---|
| `GIT_AUTH_FAILED` | 远程认证失败（凭据过期 / 无权限，不泄露凭据） |
| `GIT_REMOTE_TIMEOUT` | 远程操作超时 |
| `GIT_WORKTREE_DIRTY` | 工作区有未提交改动，操作被拒绝 |
| `GIT_CONFLICT` | 合并 / 拉取冲突，需人工解决 |
| `GIT_COMMAND_FAILED` | git 子命令非零退出（非上述分类），信息为固定提示，**不回显 stderr** |

---

## 5. 关联

- 模块：`12-git/git-architecture.md`
- 规格：`openspec/specs/git/spec.md`
- 审批：`03-interfaces/permission-interface.md`（高危操作审批链）
