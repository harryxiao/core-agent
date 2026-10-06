"""Git 版本控制核心操作（git）。

内核 loop 与调用方只依赖 GitClient 抽象；底层 git 实现经 backend 注入，
替换实现调用方零改动。叠加安全与可靠性：.git 元数据保护、高危操作审批、
异常归一（凭据经 keychain 注入，不落盘明文，见 permission-interface）。

对应接口：doc/03-interfaces/git-interface.md §1
"""

from __future__ import annotations

from collections.abc import Callable

from core.permission import AccessControlError, PermissionErrorCode

from .backend import GitBackend, build_backend
from .errors import GitError, GitErrorCode
from .models import CommitLog, GitStatus, MergeResult


class GitClient:
    """版本控制核心操作：只依赖注入的底层后端抽象。"""

    def __init__(
        self,
        *,
        backend: GitBackend | None = None,
        approval: Callable[[str], bool] | None = None,
    ) -> None:
        self._backend = backend
        self._approval = approval

    def init(self, path: str) -> str:
        """初始化仓库，返回仓库根路径。"""
        return self._require_backend().init(path)

    def clone(self, url: str, path: str, *, branch: str | None = None) -> str:
        """克隆远程仓库到本地，返回仓库根路径。"""
        return self._require_backend().clone(url, path, branch=branch)

    def commit(self, message: str, *, paths: list[str] | None = None) -> str:
        """提交工作区改动（paths 为空则全量），返回 commit id。"""
        self._guard_git_paths(paths)
        return self._require_backend().commit(message, paths=paths)

    def status(self) -> GitStatus:
        """返回工作区状态。"""
        return self._require_backend().status()

    def diff(self, *, ref: str | None = None) -> str:
        """返回与 ref（默认 HEAD）的差异。"""
        return self._require_backend().diff(ref=ref)

    def log(self, *, count: int = 20) -> list[CommitLog]:
        """返回最近 count 条提交记录。"""
        return self._require_backend().log(count=count)

    def branch(self, name: str, *, base: str | None = None) -> None:
        """基于 base（默认当前 HEAD）创建分支。"""
        self._require_backend().branch(name, base=base)

    def checkout(self, ref: str) -> None:
        """切换到指定分支 / 提交。"""
        self._require_backend().checkout(ref)

    def merge(self, branch: str) -> MergeResult:
        """合并目标分支；冲突时返回 merged=False 并报告冲突点。"""
        return self._require_backend().merge(branch)

    def stash(self, *, message: str | None = None) -> None:
        """暂存工作区改动。"""
        self._require_backend().stash(message=message)

    def stash_pop(self) -> None:
        """恢复最近一次 stash。"""
        self._require_backend().stash_pop()

    def pull(self, *, remote: str = "origin", branch: str | None = None) -> None:
        """拉取并合并远程分支。"""
        self._require_backend().pull(remote=remote, branch=branch)

    def push(
        self, *, remote: str = "origin", branch: str | None = None, force: bool = False
    ) -> None:
        """推送本地分支；force=True 属高危操作，经审批链拦截。"""
        if force:
            self._require_approval()
        self._require_backend().push(remote=remote, branch=branch, force=force)

    # ---- 内部辅助 ----

    def _require_backend(self) -> GitBackend:
        if self._backend is None:
            return build_backend()  # 未注入真实后端 → 抛「离线未接」
        return self._backend

    def _require_approval(self) -> None:
        """高危 git 操作的审批门：未获批准即 fail-closed 阻断（非交互默认拒）。

        阻断的**事由是「缺审批」而非「无权」** ⇒ 返回 `APPROVAL_REQUIRED`
        （permission 错误码表「高危操作需人工审批」/ change 0135）；
        这正是 `APPROVAL_REQUIRED` 的生产 raise 落点（此前误用 `PERMISSION_DENIED`）。
        """
        approved = self._approval("git.push(force)") if self._approval is not None else False
        if not approved:
            raise AccessControlError(
                PermissionErrorCode.APPROVAL_REQUIRED, "force-push 属高危操作，需审批通过"
            )

    @staticmethod
    def _guard_git_paths(paths: list[str] | None) -> None:
        for path in paths or []:
            if path == ".git" or path.startswith(".git/"):
                raise GitError(GitErrorCode.GIT_WORKTREE_DIRTY, "保护 .git 元数据，操作被拒绝")
