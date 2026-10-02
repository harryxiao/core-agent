"""最小可逆工具集（tool-use）。

file_read / file_write / file_patch / code_run / web_fetch 内置工具：纯读
不可逆；写类工具在处理器内先快照原内容（供撤销闭包恢复），写文件经
``EffectTracker`` 记录可逆效应，实现时间旅行回滚；code_run 子进程执行、
web_fetch 出站抓取，均经确认门（高风险需人工审批）。

对应接口：doc/03-interfaces/tool-use-interface.md §3
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import urllib.request
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
        "mode": {"type": "string", "enum": ["w", "a"]},
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

_RUN_SCHEMA = {
    "type": "object",
    "properties": {
        "script": {"type": "string"},
        "type": {"type": "string", "enum": ["python", "bash"]},
        "timeout": {"type": "number"},
        "cwd": {"type": "string"},
    },
    "required": ["script"],
}

_FETCH_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string"},
        "timeout": {"type": "number"},
    },
    "required": ["url"],
}

_MAX_OUTPUT_CHARS = 8192  # code_run stdout/stderr 截断
_MAX_FETCH_BYTES = 65536  # web_fetch 正文截断（64 KiB）
_USER_AGENT = "core-agent/0.1"


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
        # 模型侧语义值归一为 Python open 模式；未知值由 EXECUTION_FAILED 结构化兜底
        normalized = {"write": "w", "overwrite": "w", "append": "a"}.get(mode, mode)
        target = Path(path)
        snap["path"] = path
        snap["before"] = target.read_text(encoding="utf-8") if target.exists() else None
        with target.open(normalized, encoding="utf-8") as fh:
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


def code_run() -> Tool:
    """执行代码片段（python/bash 子进程，超时与输出截断；高风险经确认门）。"""

    async def handler(
        script: str, type: str = "python", timeout: float = 10.0, cwd: str | None = None
    ) -> dict[str, Any]:
        cmd = [sys.executable, "-c", script] if type == "python" else ["bash", "-c", script]
        proc = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            check=False,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        return {
            "type": type,
            "returncode": proc.returncode,
            "stdout": stdout[:_MAX_OUTPUT_CHARS],
            "stderr": stderr[:_MAX_OUTPUT_CHARS],
            "stdout_truncated": len(stdout) > _MAX_OUTPUT_CHARS,
            "stderr_truncated": len(stderr) > _MAX_OUTPUT_CHARS,
        }

    return Tool(
        definition=ToolDef(
            tool_id="tools.code_run",
            description="执行代码片段（python 或 bash），返回返回码与输出；不可逆高风险，需审批",
            schema=_RUN_SCHEMA,
            coeffects=["process:spawn", "filesystem:write"],
            reversible=False,
            timeout_s=60.0,
        ),
        handler=handler,
    )


def web_fetch() -> Tool:
    """抓取网页（GET 只读；出站网络经确认门；正文按字节截断）。"""

    def _fetch(url: str, timeout: float) -> dict[str, Any]:  # 阻塞读，经 to_thread 隔离
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"仅支持 http/https URL: {url}")  # noqa: TRY003
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(_MAX_FETCH_BYTES + 1)
        return {
            "url": url,
            "status": status,
            "content_type": content_type,
            "body": raw[:_MAX_FETCH_BYTES].decode("utf-8", errors="replace"),
            "truncated": len(raw) > _MAX_FETCH_BYTES,
        }

    async def handler(url: str, timeout: float = 15.0) -> dict[str, Any]:
        return await asyncio.to_thread(_fetch, url, timeout)

    return Tool(
        definition=ToolDef(
            tool_id="tools.web_fetch",
            description="GET 抓取网页正文（仅 http/https；出站网络，需审批）",
            schema=_FETCH_SCHEMA,
            coeffects=["network:outbound"],
            reversible=True,
            timeout_s=30.0,
        ),
        handler=handler,
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
