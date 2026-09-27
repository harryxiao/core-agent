"""Git 底层后端适配器（git）。

底层 git 实现（subprocess 直调 git CLI / gitpython / dulwich 等）收敛于
单一适配器（GitBackend），经依赖注入装配，替换实现调用方零改动；异常归一
到领域错误码。真实后端未锁选型，离线未接。

对应接口：doc/03-interfaces/git-interface.md §3
"""

from __future__ import annotations

from typing import Protocol

from .errors import GitError, GitErrorCode
from .models import CommitLog, GitStatus, MergeResult


class GitBackend(Protocol):
    """底层 git 适配器：13 项版本控制原语。"""

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


def build_backend() -> GitBackend:
    """生产 git 后端工厂：真实后端（subprocess/gitpython/dulwich）未锁选型，离线未接。"""
    raise GitError(
        GitErrorCode.GIT_REMOTE_TIMEOUT,
        "生产 git 后端需接 subprocess/gitpython/dulwich 适配器（离线未接）",
    )
