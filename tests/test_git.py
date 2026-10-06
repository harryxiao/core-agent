"""git 单元测试（对齐契约红线：核心操作往返 / .git 保护 / 高危审批 / 四错误码兜底）。"""

from __future__ import annotations

import pytest

from core.git import (
    GitClient,
    GitError,
    GitErrorCode,
    GitStatus,
    MergeResult,
    SubprocessGitBackend,
)
from core.permission import AccessControlError, PermissionErrorCode


class FakeBackend:
    """记录调用并返回受控结果的 fake git 后端。"""

    def __init__(self) -> None:
        self.commits: list[str] = []
        self.pushed: list[tuple[str, str | None, bool]] = []
        self.deleted: list[tuple[str, str]] = []
        self.amended: list[str] = []
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

    def delete_remote_branch(self, branch: str, *, remote: str = "origin") -> None:
        self.deleted.append((remote, branch))

    def rewrite_history(self, message: str) -> str:
        self.amended.append(message)
        return f"a{len(self.amended)}"


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
    """未获批准的高危推送 fail-closed：错误码为 `APPROVAL_REQUIRED`（「缺审批」非「无权」）。"""
    backend = FakeBackend()
    client = GitClient(backend=backend, approval=lambda op: False)
    with pytest.raises(AccessControlError) as exc_info:
        client.push(force=True)
    assert exc_info.value.code is PermissionErrorCode.APPROVAL_REQUIRED
    assert backend.pushed == []


def test_force_push_approved() -> None:
    backend = FakeBackend()
    GitClient(backend=backend, approval=lambda op: True).push(force=True)
    assert backend.pushed == [("origin", None, True)]


def test_push_non_force_no_approval() -> None:
    backend = FakeBackend()
    GitClient(backend=backend, approval=lambda op: False).push()
    assert backend.pushed == [("origin", None, False)]


def test_default_backend_is_subprocess_adapter() -> None:
    """change 0090：缺省后端不再是「离线未接」错误，而是 stdlib subprocess 适配器。"""
    assert isinstance(GitClient()._require_backend(), SubprocessGitBackend)


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


# ---- change 0138（账本 E79）：删除远程分支 / 历史改写 —— 同型审批门 ----


def test_delete_remote_branch_requires_approval() -> None:
    """删远程分支属高危：未批 fail-closed，且**在触碰后端前**阻断（后端零调用）。"""
    backend = FakeBackend()
    client = GitClient(backend=backend, approval=lambda op: False)
    with pytest.raises(AccessControlError) as exc_info:
        client.delete_remote_branch("feature")
    assert exc_info.value.code is PermissionErrorCode.APPROVAL_REQUIRED
    assert backend.deleted == []


def test_delete_remote_branch_approved() -> None:
    backend = FakeBackend()
    GitClient(backend=backend, approval=lambda op: True).delete_remote_branch("feature")
    assert backend.deleted == [("origin", "feature")]


def test_rewrite_history_requires_approval() -> None:
    """历史改写属高危：未批 fail-closed（非交互默认拒）。"""
    backend = FakeBackend()
    client = GitClient(backend=backend, approval=lambda op: False)
    with pytest.raises(AccessControlError) as exc_info:
        client.rewrite_history("fix: reword")
    assert exc_info.value.code is PermissionErrorCode.APPROVAL_REQUIRED
    assert backend.amended == []


def test_rewrite_history_approved() -> None:
    backend = FakeBackend()
    commit_id = GitClient(backend=backend, approval=lambda op: True).rewrite_history("fix: reword")
    assert commit_id == "a1"
    assert backend.amended == ["fix: reword"]


def test_high_risk_ops_use_distinct_approval_ids() -> None:
    """三类高危各持互异 op id：审批请求可区分「推 / 删远程分支 / 改写历史」。"""
    seen: list[str] = []
    backend = FakeBackend()
    client = GitClient(backend=backend, approval=lambda op: seen.append(op) or True)
    client.push(force=True)
    client.delete_remote_branch("feature")
    client.rewrite_history("fix: reword")
    assert seen == ["git.push(force)", "git.delete_remote_branch", "git.rewrite_history"]


def test_non_interactive_high_risk_defaults_to_denied() -> None:
    """无 `approval` 回调（非交互）恒视为未批 ⇒ 默认拒绝（与 spec「非交互默认拒绝」一致）。"""
    backend = FakeBackend()
    client = GitClient(backend=backend)
    with pytest.raises(AccessControlError):
        client.delete_remote_branch("feature")
    with pytest.raises(AccessControlError):
        client.rewrite_history("fix: reword")
    assert backend.deleted == [] and backend.amended == []
