"""Git 版本控制数据模型（git）。

工作区状态 / 提交记录 / 合并结果 三类数据结构。

对应接口：doc/03-interfaces/git-interface.md §2
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GitStatus:
    """工作区状态：当前分支 / 已改动 / 未跟踪 / 冲突文件。"""

    branch: str
    changed: list[str] = field(default_factory=list[str])
    untracked: list[str] = field(default_factory=list[str])
    conflicted: list[str] = field(default_factory=list[str])


@dataclass
class CommitLog:
    """提交记录。"""

    commit_id: str
    author: str
    message: str
    ts: str  # ISO 时间戳


@dataclass
class MergeResult:
    """合并结果：是否无冲突合并成功 + 冲突文件。"""

    merged: bool
    conflict_files: list[str] = field(default_factory=list[str])


@dataclass(frozen=True)
class WorktreeEntry:
    """`git worktree list --porcelain` 的一条记录（detached 时 branch 为 None）。"""

    path: str
    head: str
    branch: str | None = None
    bare: bool = False
    prunable: bool = False
