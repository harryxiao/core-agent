"""最小可逆工具集（tool-use）。

file_read / file_write / file_patch 三个内置工具：纯读不可逆；写类工具
在处理器内先快照原内容（供撤销闭包恢复），写文件经 ``EffectTracker``
记录可逆效应，实现时间旅行回滚。

对应接口：doc/03-interfaces/tool-use-interface.md §3
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import ToolDef
from .tool import Tool

_READ_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "start": {"type": "integer"},
        "count": {"type": "integer"},
    },
    "required": ["path"],
}

_WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "content": {"type": "string"},
        "mode": {"type": "string"},
    },
    "required": ["path", "content"],
}

_PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "old_content": {"type": "string"},
        "new_content": {"type": "string"},
    },
    "required": ["path", "old_content", "new_content"],
}


def file_read() -> Tool:
    """读文件（只读，自动放行）。"""

    def handler(path: str, start: int = 0, count: int | None = None) -> dict[str, Any]:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        selected = lines[start:] if count is None else lines[start : start + count]
        return {"path": path, "content": "\n".join(selected)}

    return Tool(
        definition=ToolDef(
            tool_id="tools.file_read",
            description="读取文本文件（可指定行范围）",
            schema=_READ_SCHEMA,
            coeffects=["filesystem:read"],
            reversible=False,
        ),
        handler=handler,
    )


def file_write() -> Tool:
    """写文件（可逆：撤销恢复原内容）。"""

    snap: dict[str, str | None] = {}

    def handler(path: str, content: str, mode: str = "w") -> dict[str, Any]:
        target = Path(path)
        snap["path"] = path
        snap["before"] = target.read_text(encoding="utf-8") if target.exists() else None
        with target.open(mode, encoding="utf-8") as fh:
            fh.write(content)
        return {"path": path, "bytes_written": len(content)}

    def undo() -> None:
        _restore(snap)

    return Tool(
        definition=ToolDef(
            tool_id="tools.file_write",
            description="写文件（可逆撤销）",
            schema=_WRITE_SCHEMA,
            coeffects=["filesystem:write"],
            reversible=True,
        ),
        handler=handler,
        undo=undo,
    )


def file_patch() -> Tool:
    """精确替换文件片段（可逆：撤销恢复原内容）。"""

    snap: dict[str, str | None] = {}

    def handler(path: str, old_content: str, new_content: str) -> dict[str, Any]:
        target = Path(path)
        original = target.read_text(encoding="utf-8")
        snap["path"] = path
        snap["before"] = original
        target.write_text(original.replace(old_content, new_content), encoding="utf-8")
        return {"path": path, "replaced": old_content in original}

    def undo() -> None:
        _restore(snap)

    return Tool(
        definition=ToolDef(
            tool_id="tools.file_patch",
            description="精确替换文件片段（可逆撤销）",
            schema=_PATCH_SCHEMA,
            coeffects=["filesystem:write"],
            reversible=True,
        ),
        handler=handler,
        undo=undo,
    )


def _restore(snap: dict[str, str | None]) -> None:
    """撤销：恢复写入前的原内容（原不存在则删除）。"""
    path = snap["path"]
    before = snap["before"]
    if path is None:
        return
    target = Path(path)
    if before is None:
        target.unlink(missing_ok=True)
    else:
        target.write_text(before, encoding="utf-8")
