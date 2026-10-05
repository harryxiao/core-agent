"""stdlib subprocess 直调 git CLI 的生产后端（git）。

生产**缺省** git 后端：以 stdlib ``subprocess`` 直调 ``git`` CLI，**零第三方依赖**（不引入
gitpython / dulwich）。异常归一为领域错误码（认证失败 / 超时 / 冲突 / 通用命令失败）；**错误信息
不回显原始 stderr** —— git 的 stderr 可能含带凭据的远程地址。凭据由环境中的 git credential
helper 处理：本模块不接触、不落盘、不进日志。

对应接口：doc/03-interfaces/git-interface.md §3
"""

from __future__ import annotations

import subprocess
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

# porcelain 行前缀宽度：XY 状态 2 字符 + 1 空格
_PORCELAIN_PREFIX = 3

# log 解析用不可打印分隔符，避免提交信息里的空格 / 竖线污染字段切分
_FIELD_SEP = "\x1f"
_LOG_FORMAT = f"%H{_FIELD_SEP}%an{_FIELD_SEP}%s{_FIELD_SEP}%aI"


def _is_conflict(code: str) -> bool:
    """porcelain XY 码是否表示冲突：任一侧 `U`（未合并），或双方同增 `AA` / 同删 `DD`。"""
    return "U" in code or code in ("AA", "DD")


class SubprocessGitBackend:
    """以 stdlib ``subprocess`` 直调 git CLI 的 :class:`GitBackend` 生产实现。"""

    def __init__(self, cwd: str | Path | None = None, *, timeout: float = 60.0) -> None:
        self._cwd = Path(cwd) if cwd is not None else Path.cwd()
        self._timeout = timeout

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
        self._run(*args)
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
        self._run(*args)

    def push(
        self, *, remote: str = "origin", branch: str | None = None, force: bool = False
    ) -> None:
        args = ["push"]
        if force:
            args.append("--force")
        args.append(remote)
        if branch is not None:
            args.append(branch)
        self._run(*args)

    # ---- 内部辅助 ----

    def _run(self, *args: str, cwd: Path | None = None) -> str:
        """执行 git 子命令，非零退出 ⇒ 抛归一后的结构化 `GitError`，返回 stdout。"""
        result = self._invoke(args, cwd=cwd)
        if result.returncode != 0:
            raise self._classify(result.stderr)
        return result.stdout

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
