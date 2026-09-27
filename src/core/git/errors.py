"""Git 版本控制领域错误码（git）。

结构化错误码与异常分离，供 GitClient 抛出。

对应接口：doc/03-interfaces/git-interface.md §4
"""

from __future__ import annotations

from enum import StrEnum


class GitErrorCode(StrEnum):
    """Git 结构化错误码。"""

    GIT_AUTH_FAILED = "GIT_AUTH_FAILED"
    GIT_REMOTE_TIMEOUT = "GIT_REMOTE_TIMEOUT"
    GIT_WORKTREE_DIRTY = "GIT_WORKTREE_DIRTY"
    GIT_CONFLICT = "GIT_CONFLICT"


class GitError(Exception):
    """Git 业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: GitErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
