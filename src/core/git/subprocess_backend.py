"""stdlib subprocess 直调 git CLI 的生产后端（git）。

生产**缺省** git 后端：以 stdlib ``subprocess`` 直调 ``git`` CLI，**零第三方依赖**（不引入
gitpython / dulwich）。异常归一为领域错误码（认证失败 / 超时 / 冲突 / 通用命令失败）；**错误信息
不回显原始 stderr** —— git 的 stderr 可能含带凭据的远程地址。凭据由环境中的 git credential
helper 处理：本模块不接触、不落盘、不进日志。

对应接口：doc/03-interfaces/git-interface.md §3
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from .errors import GitError, GitErrorCode
from .models import CommitLog, GitStatus, MergeResult

# 认证失败的可识别特征（大小写不敏感；仅用于归类，不回显原文）
_AUTH_MARKERS = (
    "authentication failed",
    "could not read username",
    "could not read password",
    "permission denied (publickey)",
    "invalid username or password",
    "terminal prompts disabled",
)

# 瞬时网络故障的可识别特征（大小写不敏感；仅决定「可重试」，不回显原文）
_TRANSIENT_MARKERS = (
    "could not resolve host",
    "connection reset",
    "connection refused",
    "connection timed out",
    "network is unreachable",
    "rpc failed",
    "early eof",
    "the remote end hung up unexpectedly",
    "temporary failure in name resolution",
)

# porcelain 行前缀宽度：XY 状态 2 字符 + 1 空格
_PORCELAIN_PREFIX = 3

# log 解析用不可打印分隔符，避免提交信息里的空格 / 竖线污染字段切分
_FIELD_SEP = "\x1f"
_LOG_FORMAT = f"%H{_FIELD_SEP}%an{_FIELD_SEP}%s{_FIELD_SEP}%aI"


def _is_conflict(code: str) -> bool:
    """porcelain XY 码是否表示冲突：任一侧 `U`（未合并），或双方同增 `AA` / 同删 `DD`。"""
    return "U" in code or code in ("AA", "DD")


def _is_retryable(error: GitError, stderr: str) -> bool:
    """是否值得重试：**仅**「瞬时网络」类（通用失败码 + stderr 命中瞬态特征）。

    认证失败（凭据不会自愈）/ 超时（spec「远程超时」要求中止）/ 冲突（需人工）一律不重试；
    「非仓库目录」这类确定性 `GIT_COMMAND_FAILED` 亦不命中瞬态特征 ⇒ 一次即抛。
    """
    if error.code is not GitErrorCode.GIT_COMMAND_FAILED:
        return False
    lowered = stderr.lower()
    return any(marker in lowered for marker in _TRANSIENT_MARKERS)


class SubprocessGitBackend:
    """以 stdlib ``subprocess`` 直调 git CLI 的 :class:`GitBackend` 生产实现。"""

    def __init__(
        self,
        cwd: str | Path | None = None,
        *,
        timeout: float = 60.0,
        attempts: int = 3,
        backoff: float = 0.5,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._cwd = Path(cwd) if cwd is not None else Path.cwd()
        self._timeout = timeout
        self._attempts = max(1, attempts)  # 远程操作最大尝试次数（含首次）
        self._backoff = backoff  # 指数退避基数（秒）：n 次退避 = backoff * 2**(n-1)
        self._sleep = sleep if sleep is not None else time.sleep  # 可注入 ⇒ 测试零真实等待

    # ---- 仓库生命周期 ----

    def init(self, path: str) -> str:
        root = Path(path)
        root.mkdir(parents=True, exist_ok=True)
        self._run("init", cwd=root)
        self._cwd = root
        return str(root)

    def clone(self, url: str, path: str, *, branch: str | None = None) -> str:
        root = Path(path)
        args = ["clone"]
        if branch is not None:
            args += ["--branch", branch]
        args += [url, str(root)]
        self._run_remote(*args)
        self._cwd = root
        return str(root)

    # ---- 本地操作 ----

    def commit(self, message: str, *, paths: list[str] | None = None) -> str:
        if paths:
            self._run("add", "--", *paths)
        else:
            self._run("add", "-A")
        self._run("commit", "-m", message)
        return self._run("rev-parse", "HEAD").strip()

    def status(self) -> GitStatus:
        out = self._run("status", "--porcelain", "--branch")
        branch = ""
        changed: list[str] = []
        untracked: list[str] = []
        conflicted: list[str] = []
        for line in out.splitlines():
            if line.startswith("## "):
                branch = self._parse_branch(line[3:])
                continue
            if len(line) < _PORCELAIN_PREFIX:
                continue
            code, path = line[:2], line[_PORCELAIN_PREFIX:]
            if code == "??":
                untracked.append(path)
            elif _is_conflict(code):
                conflicted.append(path)
            else:
                changed.append(path)
        return GitStatus(branch=branch, changed=changed, untracked=untracked, conflicted=conflicted)

    def diff(self, *, ref: str | None = None) -> str:
        return self._run("diff", ref) if ref is not None else self._run("diff")

    def log(self, *, count: int = 20) -> list[CommitLog]:
        out = self._run("log", f"-n{count}", f"--pretty=format:{_LOG_FORMAT}")
        entries: list[CommitLog] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            commit_id, author, message, ts = line.split(_FIELD_SEP, 3)
            entries.append(CommitLog(commit_id=commit_id, author=author, message=message, ts=ts))
        return entries

    def branch(self, name: str, *, base: str | None = None) -> None:
        if base is not None:
            self._run("branch", name, base)
        else:
            self._run("branch", name)

    def checkout(self, ref: str) -> None:
        self._run("checkout", ref)

    def merge(self, branch: str) -> MergeResult:
        result = self._invoke(("merge", branch))
        if result.returncode == 0:
            return MergeResult(merged=True)
        conflicts = self._conflicted_files()
        if conflicts:
            return MergeResult(merged=False, conflict_files=conflicts)
        raise self._classify(result.stderr)

    def stash(self, *, message: str | None = None) -> None:
        if message is not None:
            self._run("stash", "push", "-m", message)
        else:
            self._run("stash")

    def stash_pop(self) -> None:
        self._run("stash", "pop")

    # ---- 远程操作 ----

    def pull(self, *, remote: str = "origin", branch: str | None = None) -> None:
        args = ["pull", remote] + ([branch] if branch is not None else [])
        self._run_remote(*args)

    def push(
        self, *, remote: str = "origin", branch: str | None = None, force: bool = False
    ) -> None:
        args = ["push"]
        if force:
            args.append("--force")
        args.append(remote)
        if branch is not None:
            args.append(branch)
        self._run_remote(*args)

    def delete_remote_branch(self, branch: str, *, remote: str = "origin") -> None:
        """删除远程分支（`git push <remote> --delete <branch>`）；高危 ⇒ 审批门在 `GitClient`。"""
        self._run_remote("push", remote, "--delete", branch)

    def rewrite_history(self, message: str) -> str:
        """改写历史：`git commit --amend` 最近一次提交并返回新 commit id；高危 ⇒ 审批门在上层。"""
        self._run("commit", "--amend", "-m", message)
        return self._run("rev-parse", "HEAD").strip()

    # ---- 内部辅助 ----

    def _run(self, *args: str, cwd: Path | None = None) -> str:
        """执行 git 子命令，非零退出 ⇒ 抛归一后的结构化 `GitError`，返回 stdout。"""
        result = self._invoke(args, cwd=cwd)
        if result.returncode != 0:
            raise self._classify(result.stderr)
        return result.stdout

    def _run_remote(self, *args: str) -> str:
        """执行**远程** git 子命令：瞬态错误按指数退避重试，至 `attempts` 上限后抛归一错误。

        只用于 `clone` / `pull` / `push` / `delete_remote_branch`（本地原语失败重试无意义）；
        认证失败 / 超时 / 冲突 / 非瞬态失败 **不**重试（见 `_is_retryable`）。
        """
        attempt = 1
        while True:
            result = self._invoke(args)
            if result.returncode == 0:
                return result.stdout
            error = self._classify(result.stderr)
            if attempt >= self._attempts or not _is_retryable(error, result.stderr):
                raise error
            self._sleep(self._backoff * 2 ** (attempt - 1))
            attempt += 1

    def _invoke(
        self, args: tuple[str, ...], *, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=str(cwd if cwd is not None else self._cwd),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise GitError(GitErrorCode.GIT_COMMAND_FAILED, "未找到 git 可执行文件") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitError(GitErrorCode.GIT_REMOTE_TIMEOUT, "git 操作超时") from exc

    @staticmethod
    def _classify(stderr: str) -> GitError:
        """按 stderr 特征归类（**不回显原文** —— 可能含凭据 / 私有仓库地址）。"""
        lowered = stderr.lower()
        if any(marker in lowered for marker in _AUTH_MARKERS):
            return GitError(GitErrorCode.GIT_AUTH_FAILED, "git 远程认证失败")
        if "conflict" in lowered:
            return GitError(GitErrorCode.GIT_CONFLICT, "git 操作冲突，需人工解决")
        return GitError(GitErrorCode.GIT_COMMAND_FAILED, "git 命令执行失败")

    def _conflicted_files(self) -> list[str]:
        out = self._run("diff", "--name-only", "--diff-filter=U")
        return [line for line in out.splitlines() if line.strip()]

    @staticmethod
    def _parse_branch(text: str) -> str:
        """从 `## ` 行取分支名：去 upstream（`a...origin/a`）；`No commits yet on b` → `b`。"""
        name = text.split("...", 1)[0]
        if name.startswith("No commits yet on "):
            name = name[len("No commits yet on ") :]
        return name.strip()
