"""Git 底层后端适配器（git）。

底层 git 实现（subprocess 直调 git CLI / gitpython / dulwich 等）收敛于
单一适配器（GitBackend），经依赖注入装配，替换实现调用方零改动；异常归一
到领域错误码。真实后端未锁选型，离线未接。

对应接口：doc/03-interfaces/git-interface.md §3
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import CommitLog, GitStatus, MergeResult, WorktreeEntry
from .subprocess_backend import SubprocessGitBackend


class GitBackend(Protocol):
    """底层 git 适配器：21 项版本控制原语（含 6 项工作树/分支原语）。"""

    def init(self, path: str) -> str: ...

    def clone(self, url: str, path: str, *, branch: str | None = None) -> str: ...

    def commit(self, message: str, *, paths: list[str] | None = None) -> str: ...

    def status(self) -> GitStatus: ...

    def diff(self, *, ref: str | None = None) -> str: ...

    def log(self, *, count: int = 20) -> list[CommitLog]: ...

    def branch(self, name: str, *, base: str | None = None) -> None: ...

    def checkout(self, ref: str) -> None: ...

    def merge(self, branch: str) -> MergeResult: ...

    def stash(self, *, message: str | None = None) -> None: ...

    def stash_pop(self) -> None: ...

    def pull(self, *, remote: str = "origin", branch: str | None = None) -> None: ...

    def push(
        self, *, remote: str = "origin", branch: str | None = None, force: bool = False
    ) -> None: ...

    def delete_remote_branch(self, branch: str, *, remote: str = "origin") -> None: ...

    def rewrite_history(self, message: str) -> str: ...

    # ---- 工作树 / 分支原语（本地操作；change 0284）----

    def repo_root(self) -> str: ...

    def worktree_add(self, path: str, *, branch: str, base: str = "HEAD") -> None: ...

    def worktree_list(self) -> list[WorktreeEntry]: ...

    def worktree_remove(self, path: str, *, force: bool = False) -> None: ...

    def branch_exists(self, name: str) -> bool: ...

    def delete_branch(self, name: str, *, force: bool = False) -> None: ...


def build_backend(cwd: str | Path | None = None) -> GitBackend:
    """生产 git 后端工厂：stdlib ``subprocess`` 直调 git CLI（零第三方依赖，change 0090）。

    真实后端实现见 :class:`core.git.subprocess_backend.SubprocessGitBackend`；如将来改用
    gitpython / dulwich，仅替换本工厂，调用方零改动。`cwd` 为空时沿用进程当前目录。
    """
    return SubprocessGitBackend(cwd)
