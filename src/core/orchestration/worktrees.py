"""子 Agent 工作树管理器与租约（change 0284 / ADR-0274）。

每次 `tools.delegate` 在宿主仓库的独立 git worktree 中运行；终态**保留**工作树与分支，
由显式 `discard` 清理。布局：`<root>/<repo_key>/<worktree_id>/` + 同名 sidecar（0600）。

对应规格：doc/openspec/specs/orchestration/spec.md「子 Agent 工作树隔离」。
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from core.git import GitBackend, GitError, GitErrorCode, build_backend
from core.tools import Tool, ToolDef

from .errors import OrchestrationError, OrchestrationErrorCode
from .state_files import atomic_write_json, exclusive_file_lock

WORKTREE_ID_RE = re.compile(r"^wt-[0-9a-f]{12}$")
BRANCH_PREFIX = "core-agent/"
_SIDECAR_VERSION = 1
_MAX_CHANGED_FILES = 20
_MAX_LIST = 50

_LIST_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}
_DISCARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "worktree_id": {"type": "string"},
        "force": {"type": "boolean"},
    },
    "required": ["worktree_id"],
}


@dataclass(frozen=True)
class WorkspaceLease:
    """一次委托的工作树租约（创建后只读）。"""

    worktree_id: str
    repo_root: str
    path: str
    branch: str
    agent_id: str
    created_at: float

    def as_metadata(self, changed: list[str] | None = None) -> dict[str, Any]:
        """工具结果 / 后台登记使用的元数据（不含任务正文）。"""
        return {
            "id": self.worktree_id,
            "path": self.path,
            "branch": self.branch,
            "repo_root": self.repo_root,
            "changed_files": list(changed or []),
        }


def changed_files(lease: WorkspaceLease, *, cap: int = _MAX_CHANGED_FILES) -> list[str]:
    """best-effort 统计工作树改动：失败返回空列表，绝不影响任务结果。"""
    try:
        status = build_backend(lease.path).status()
    except (GitError, OSError):
        return []
    names = {*status.changed, *status.untracked, *status.conflicted}
    return sorted(names)[:cap]


class WorktreeManager:
    """管理状态根下的一组隔离工作树（创建 / 清单 / 显式丢弃）。"""

    def __init__(
        self,
        root: Path | str,
        *,
        backend_factory: Callable[[str | Path | None], GitBackend] = build_backend,
        max_list: int = _MAX_LIST,
    ) -> None:
        self._root = Path(root).expanduser()
        self._backend_factory = backend_factory
        self._max_list = max_list

    @property
    def root(self) -> Path:
        return self._root

    def create(self, *, agent_id: str, start: Path | str | None = None) -> WorkspaceLease:
        """创建独立工作树与分支；任一前置条件不满足 ⇒ `WORKTREE_UNAVAILABLE`。"""
        backend = self._backend_factory(start)
        repo_root = self._repo_root(backend)
        self._ensure_outside_repo(repo_root)
        worktree_id = f"wt-{uuid.uuid4().hex[:12]}"
        repo_key = _repo_key(repo_root)
        path = self._root / repo_key / worktree_id
        branch = f"{BRANCH_PREFIX}{worktree_id}"
        self._prepare_dir(path.parent)
        if path.exists() or path.is_symlink():
            raise _unavailable("工作树目录已存在")
        try:
            backend.worktree_add(str(path), branch=branch)
            atomic_write_json(
                self._sidecar(repo_key, worktree_id),
                _record(worktree_id, repo_root, path, branch, agent_id),
            )
        except (GitError, OSError) as exc:
            self._rollback_create(backend, path, branch)
            raise _unavailable(  # noqa: TRY003 — 用户可读的领域说明
                "无法创建隔离工作树（须为含至少一次提交的 git 仓库）"
            ) from exc
        return WorkspaceLease(
            worktree_id=worktree_id,
            repo_root=str(repo_root),
            path=str(path),
            branch=branch,
            agent_id=agent_id,
            created_at=time.time(),
        )

    def list(self) -> dict[str, Any]:
        """按创建时间倒序返回 sidecar 记录（最多 `max_list` 条），不触发 git 扫描。"""
        records = self._sidecar_records()
        records.sort(key=lambda item: _float(item.get("created_at")), reverse=True)
        items = [_list_item(record) for record in records[: self._max_list]]
        return {"worktrees": items, "truncated": len(records) > self._max_list}

    def discard(self, worktree_id: str, *, force: bool = False) -> dict[str, Any]:
        """显式丢弃工作树与分支；id 不存在时幂等返回成功。"""
        if not WORKTREE_ID_RE.match(worktree_id):
            return {"ok": False, "error": "非法工作树 id"}
        sidecar = self._find_sidecar(worktree_id)
        if sidecar is None:
            return {"ok": True, "worktree_id": worktree_id, "removed": False, "reason": "not_found"}
        with exclusive_file_lock(sidecar):
            return self._discard_locked(worktree_id, sidecar, force=force)

    def remove_quiet(self, lease: WorkspaceLease) -> None:
        """创建后续步骤失败时的 best-effort 清理（不向调用方抛异常）。"""
        with contextlib.suppress(Exception):
            self.discard(lease.worktree_id, force=True)

    # ---- 内部辅助 ----

    def _repo_root(self, backend: GitBackend) -> Path:
        try:
            root = backend.repo_root()
        except GitError as exc:
            raise _unavailable(  # noqa: TRY003 — 用户可读的领域说明
                "当前目录不是 git 仓库（或无法解析仓库根）"
            ) from exc
        if not root:
            raise _unavailable("无法解析 git 仓库根")  # noqa: TRY003 — 用户可读的领域说明
        return Path(root).resolve()

    def _ensure_outside_repo(self, repo_root: Path) -> None:
        root = self._root.resolve()
        if root == repo_root or root.is_relative_to(repo_root):
            raise _unavailable("状态目录不得位于仓库内")

    def _prepare_dir(self, parent: Path) -> None:
        parent.mkdir(parents=True, exist_ok=True)
        for directory in (self._root, parent):
            with contextlib.suppress(OSError):
                directory.chmod(0o700)

    def _sidecar(self, repo_key: str, worktree_id: str) -> Path:
        return self._root / repo_key / f"{worktree_id}.json"

    def _rollback_create(self, backend: GitBackend, path: Path, branch: str) -> None:
        with contextlib.suppress(GitError, OSError):
            if path.exists():
                backend.worktree_remove(str(path), force=True)
        with contextlib.suppress(GitError, OSError):
            if backend.branch_exists(branch):
                backend.delete_branch(branch, force=True)

    def _sidecar_records(self) -> list[dict[str, Any]]:
        if not self._root.exists():
            return []
        records: list[dict[str, Any]] = []
        for sidecar in self._root.glob("*/*.json"):
            record = _read_sidecar(sidecar)
            if record is not None:
                records.append(record)
        return records

    def _find_sidecar(self, worktree_id: str) -> Path | None:
        for candidate in self._root.glob(f"*/{worktree_id}.json"):
            return candidate
        return None

    def _discard_locked(self, worktree_id: str, sidecar: Path, *, force: bool) -> dict[str, Any]:
        record = _read_sidecar(sidecar)
        if record is None or record.get("id") != worktree_id:
            return {"ok": False, "error": "工作树登记无效"}
        if not _record_valid(record, self._root, sidecar, worktree_id):
            return {"ok": False, "error": "工作树登记无效（路径越界），拒绝删除"}
        return self._remove_record(record, sidecar, force=force)

    def _remove_record(
        self, record: dict[str, Any], sidecar: Path, *, force: bool
    ) -> dict[str, Any]:
        path = cast("str", record["path"])
        branch = cast("str", record["branch"])
        backend = self._backend_factory(cast("str", record["repo_root"]))
        failure = self._remove_worktree(backend, path, force=force)
        if failure is not None:
            return failure
        branch_deleted = self._delete_branch(backend, branch)
        if branch_deleted is None:
            return {"ok": False, "error": "删除工作树分支失败"}
        sidecar.unlink(missing_ok=True)
        return {
            "ok": True,
            "worktree_id": record["id"],
            "removed": True,
            "branch_deleted": branch_deleted,
        }

    @staticmethod
    def _remove_worktree(backend: GitBackend, path: str, *, force: bool) -> dict[str, Any] | None:
        if not Path(path).exists():
            return None
        try:
            backend.worktree_remove(path, force=force)
        except GitError as exc:
            if exc.code is GitErrorCode.GIT_WORKTREE_DIRTY and not force:
                return {"ok": False, "error": "工作树含未提交改动；如需强制丢弃请传 force=true"}
            return {"ok": False, "error": f"丢弃工作树失败: {exc.code.value}"}
        except OSError:
            return {"ok": False, "error": "丢弃工作树失败: 文件系统错误"}
        return None

    @staticmethod
    def _delete_branch(backend: GitBackend, branch: str) -> bool | None:
        """删除分支；返回是否删除，失败返回 None（sidecar 保留以便重试）。"""
        try:
            if not backend.branch_exists(branch):
                return False
            backend.delete_branch(branch, force=True)
        except (GitError, OSError):
            return None
        return True


def worktree_tools(
    *, manager: WorktreeManager, is_running: Callable[[str], str | None]
) -> tuple[Tool, Tool]:
    """工作树清单（只读）与显式丢弃（HIGH_RISK）工具；仅挂主工具面。"""

    async def list_handler() -> dict[str, Any]:
        return await asyncio.to_thread(manager.list)

    async def discard_handler(worktree_id: str, force: bool = False) -> dict[str, Any]:
        busy = is_running(worktree_id)
        if busy is not None:
            return {"ok": False, "error": f"工作树正被后台任务占用: {busy}"}
        return await asyncio.to_thread(manager.discard, worktree_id, force=force)

    return (
        Tool(
            definition=ToolDef(
                tool_id="tools.worktree.list",
                description="列出子 Agent 隔离工作树（只读，自动放行）",
                schema=_LIST_SCHEMA,
                coeffects=["worktree:read"],
                reversible=True,
                timeout_s=10.0,
            ),
            handler=list_handler,
        ),
        Tool(
            definition=ToolDef(
                tool_id="tools.worktree.discard",
                description="显式丢弃隔离工作树与分支（不可逆，需审批；force 丢弃未提交改动）",
                schema=_DISCARD_SCHEMA,
                coeffects=["worktree:write"],
                reversible=False,
                timeout_s=60.0,
            ),
            handler=discard_handler,
        ),
    )


def _unavailable(detail: str) -> OrchestrationError:
    return OrchestrationError(OrchestrationErrorCode.WORKTREE_UNAVAILABLE, detail)


def _repo_key(repo_root: Path) -> str:
    return hashlib.sha256(str(repo_root).encode("utf-8")).hexdigest()[:12]


def _record(
    worktree_id: str, repo_root: Path, path: Path, branch: str, agent_id: str
) -> dict[str, Any]:
    return {
        "version": _SIDECAR_VERSION,
        "id": worktree_id,
        "repo_root": str(repo_root),
        "path": str(path),
        "branch": branch,
        "agent_id": agent_id,
        "created_at": time.time(),
    }


def _read_sidecar(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    record = cast(dict[str, Any], raw)
    worktree_id = record.get("id")
    if not isinstance(worktree_id, str) or not WORKTREE_ID_RE.match(worktree_id):
        return None
    return record


def _record_valid(record: dict[str, Any], root: Path, sidecar: Path, worktree_id: str) -> bool:
    """校验登记未被篡改：精确布局 + 分支名 + sidecar 位于状态根内。"""
    if record.get("branch") != f"{BRANCH_PREFIX}{worktree_id}":
        return False
    path = record.get("path")
    if not isinstance(path, str):
        return False
    expected = root.resolve() / sidecar.parent.name / worktree_id
    return Path(path).resolve() == expected and sidecar.resolve().is_relative_to(root.resolve())


def _list_item(record: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(record.get("path", "")))
    return {
        "id": record.get("id"),
        "path": record.get("path"),
        "branch": record.get("branch"),
        "repo_root": record.get("repo_root"),
        "agent_id": record.get("agent_id"),
        "created_at": record.get("created_at"),
        "exists": path.exists(),
    }


def _float(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0
