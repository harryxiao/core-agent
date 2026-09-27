"""git 单元测试（对齐契约红线：核心操作往返 / .git 保护 / 高危审批 / 四错误码兜底）。"""

from __future__ import annotations

import pytest

from core.git import GitClient, GitError, GitErrorCode, GitStatus, MergeResult
from core.permission import AccessControlError


class FakeBackend:
    """记录调用并返回受控结果的 fake git 后端。"""

    def __init__(self) -> None:
        self.commits: list[str] = []
        self.pushed: list[tuple[str, str | None, bool]] = []
        self.auth_fail = False
        self.merge_conflict = False

    def init(self, path: str) -> str:
        return path

    def clone(self, url: str, path: str, *, branch: str | None = None) -> str:
        return path

    def commit(self, message: str, *, paths: list[str] | None = None) -> str:
        self.commits.append(message)
        return f"c{len(self.commits)}"

    def status(self) -> GitStatus:
        return GitStatus(branch="main")

    def diff(self, *, ref: str | None = None) -> str:
        return ""

    def log(self, *, count: int = 20) -> list:
        return []

    def branch(self, name: str, *, base: str | None = None) -> None:
        return None

    def checkout(self, ref: str) -> None:
        return None

    def merge(self, branch: str) -> MergeResult:
        if self.merge_conflict:
            raise GitError(GitErrorCode.GIT_CONFLICT, "合并冲突")
        return MergeResult(merged=True)

    def stash(self, *, message: str | None = None) -> None:
        return None

    def stash_pop(self) -> None:
        return None

    def pull(self, *, remote: str = "origin", branch: str | None = None) -> None:
        return None

    def push(
        self, *, remote: str = "origin", branch: str | None = None, force: bool = False
    ) -> None:
        if self.auth_fail:
            raise GitError(GitErrorCode.GIT_AUTH_FAILED, "401")
        self.pushed.append((remote, branch, force))


def test_init_commit_status_roundtrip() -> None:
    backend = FakeBackend()
    client = GitClient(backend=backend)
    assert client.init("/repo") == "/repo"
    assert client.commit("feat: x") == "c1"
    assert client.status().branch == "main"
    assert backend.commits == ["feat: x"]


def test_git_metadata_protection() -> None:
    client = GitClient(backend=FakeBackend())
    with pytest.raises(GitError) as exc_info:
        client.commit("bad", paths=[".git/config"])
    assert exc_info.value.code is GitErrorCode.GIT_WORKTREE_DIRTY


def test_force_push_requires_approval() -> None:
    backend = FakeBackend()
    client = GitClient(backend=backend, approval=lambda op: False)
    with pytest.raises(AccessControlError):
        client.push(force=True)
    assert backend.pushed == []


def test_force_push_approved() -> None:
    backend = FakeBackend()
    GitClient(backend=backend, approval=lambda op: True).push(force=True)
    assert backend.pushed == [("origin", None, True)]


def test_push_non_force_no_approval() -> None:
    backend = FakeBackend()
    GitClient(backend=backend, approval=lambda op: False).push()
    assert backend.pushed == [("origin", None, False)]


def test_no_backend_raises() -> None:
    client = GitClient()
    with pytest.raises(GitError) as exc_info:
        client.commit("x")
    assert exc_info.value.code is GitErrorCode.GIT_REMOTE_TIMEOUT


def test_backend_auth_failed() -> None:
    backend = FakeBackend()
    backend.auth_fail = True
    client = GitClient(backend=backend, approval=lambda op: True)
    with pytest.raises(GitError) as exc_info:
        client.push()
    assert exc_info.value.code is GitErrorCode.GIT_AUTH_FAILED


def test_backend_conflict() -> None:
    backend = FakeBackend()
    backend.merge_conflict = True
    with pytest.raises(GitError) as exc_info:
        GitClient(backend=backend).merge("feature")
    assert exc_info.value.code is GitErrorCode.GIT_CONFLICT
