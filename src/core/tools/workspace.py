"""工作区上下文（tools）。

子 Agent 工作树隔离经 ``ContextVar`` 承载「当前工作区根」：文件工具的**相对路径**与
``code_run`` 省略 ``cwd`` 时的缺省目录相对该根解析。``asyncio.create_task`` 与
``asyncio.to_thread`` 都会传播 context，因此按任务隔离、无需改动共享的 loop / provider。

只影响相对路径：绝对路径、``~`` 展开结果与符号链接目标保持原语义 —— 这是路径作用域，
**不是安全沙箱**（change 0284 / ADR-0274）。本模块仅依赖 stdlib。
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_WORKSPACE_ROOT: ContextVar[Path | None] = ContextVar("core_workspace_root", default=None)


def workspace_root() -> Path | None:
    """当前任务的工作区根；未隔离时返回 None。"""
    return _WORKSPACE_ROOT.get()


@contextmanager
def use_workspace(root: Path | str | None) -> Generator[None, None, None]:
    """在上下文内把相对路径解析到 ``root``；退出（含异常）时恢复原值。"""
    token = _WORKSPACE_ROOT.set(Path(root) if root is not None else None)
    try:
        yield
    finally:
        _WORKSPACE_ROOT.reset(token)


def resolve_path(path: str | Path) -> Path:
    """按工作区解析路径：先展开 ``~``；绝对路径 / 盘符相对路径原样返回。"""
    expanded = Path(path).expanduser()
    if expanded.is_absolute() or expanded.drive:
        return expanded
    root = _WORKSPACE_ROOT.get()
    return root / expanded if root is not None else expanded
