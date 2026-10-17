"""最小可逆工具集（tool-use）。

file_read / file_write / file_patch / code_run / web_fetch 内置工具：纯读
不可逆；写类工具在处理器内先快照原内容（供撤销闭包恢复），写文件经
``EffectTracker`` 记录可逆效应，实现时间旅行回滚；code_run 子进程执行、
web_fetch 出站抓取，均经确认门（高风险需人工审批）。

另含 **gate_run**（change 0111）：把交付流水线既有的四道质量门禁暴露为工具面，
门禁名与命令取自单一真源，**执行器由组合根注入**（本层不依赖 L5）。

另含 **context_read**（change 0140）：信息地图取详情（按指针取片段，不加载全文），
取数器同样**由组合根注入**（本层不依赖 context 层）。

对应接口：doc/03-interfaces/tool-use-interface.md §3
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from .env_shell import (
    EnvironmentSnapshot,
    probe_environment,
    resolve_run_type,
    shell_argv,
)
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

# PowerShell 5.1 与 7+ 通用：把控制台/管道输出统一为无 BOM UTF-8，与父进程解码配对。
_PS_UTF8_PREAMBLE = (
    "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; "
    "$OutputEncoding = [Console]::OutputEncoding"
)

_RUN_SCHEMA = {
    "type": "object",
    "properties": {
        "script": {"type": "string"},
        "type": {
            "type": "string",
            "enum": ["python", "bash", "powershell"],
            "description": (
                "python=解释器 -c；bash / powershell=对应壳。"
                "显式 type 优先于平台缺省；省略时：Windows→powershell，Darwin/Linux→bash。"
            ),
        },
        "timeout": {"type": "number", "description": "超时秒数（缺省 10）"},
        "cwd": {
            "type": "string",
            "description": "工作目录（绝对路径；支持 ~ 展开；每次调用独立）",
        },
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


def _expand(path: str) -> Path:
    """把用户侧路径归一为 ``Path``：**展开 ``~``**（家目录，change 0228 / ADR-0218）。

    ``Path`` 不做 ``~`` 展开 ⇒ 模型写 ``~/.core/…`` 会被当作**当前工作目录下字面名为 ``~``
    的目录**下的文件（父目录不存在 ⇒ ``FileNotFoundError``）。与 ``core_profile.loader`` 的
    ``Path(path).expanduser()`` 同口径；只展开 ``~``（``~user`` 一并处理），不 ``resolve`` /
    不 ``abspath`` / 不展开环境变量。对无 ``~`` 的路径是**恒等变换**。
    """
    return Path(path).expanduser()


def file_read() -> Tool:
    """读文件（只读，自动放行）。"""

    def handler(path: str, start: int = 0, count: int | None = None) -> dict[str, Any]:
        lines = _expand(path).read_text(encoding="utf-8").splitlines()
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

    # 每次调用**各持一份**快照（LIFO）：工具实例跨调用复用，撤销第 N 次须还原该次写入前的
    # 内容，SHALL NOT 被后续调用覆写（change 0129 / E64）。
    snaps: list[dict[str, str | None]] = []

    def handler(path: str, content: str, mode: str = "w") -> dict[str, Any]:
        # 模型侧语义值归一为 Python open 模式；未知值由 EXECUTION_FAILED 结构化兜底
        normalized = {"write": "w", "overwrite": "w", "append": "a"}.get(mode, mode)
        target = _expand(path)
        before = target.read_text(encoding="utf-8") if target.exists() else None
        with target.open(normalized, encoding="utf-8") as fh:
            fh.write(content)
        # 快照存**展开后**路径 ⇒ `_restore` 恢复点与写入点一致（change 0228 / ADR-0218）
        snaps.append({"path": str(target), "before": before})  # 写入**成功后**压栈
        return {"path": path, "bytes_written": len(content)}

    def undo() -> Callable[[], None]:
        """取**本次**调用的撤销闭包：LIFO 弹出该次快照（空栈 ⇒ no-op）。"""
        snap: dict[str, str | None] = snaps.pop() if snaps else {"path": None, "before": None}
        return lambda: _restore(snap)

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

    # 同 file_write：每次调用各持一份快照，回滚逐次各归各位（change 0129 / E64）。
    snaps: list[dict[str, str | None]] = []

    def handler(path: str, old_content: str, new_content: str) -> dict[str, Any]:
        target = _expand(path)
        original = target.read_text(encoding="utf-8")
        target.write_text(original.replace(old_content, new_content), encoding="utf-8")
        # 快照存**展开后**路径 ⇒ `_restore` 恢复点与写入点一致（change 0228 / ADR-0218）
        snaps.append({"path": str(target), "before": original})  # 写入**成功后**压栈
        return {"path": path, "replaced": old_content in original}

    def undo() -> Callable[[], None]:
        """取**本次**调用的撤销闭包：LIFO 弹出该次快照（空栈 ⇒ no-op）。"""
        snap: dict[str, str | None] = snaps.pop() if snaps else {"path": None, "before": None}
        return lambda: _restore(snap)

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


def code_run(
    *,
    env_snapshot: EnvironmentSnapshot | Callable[[], EnvironmentSnapshot] | None = None,
) -> Tool:
    """执行代码片段（python / bash / powershell；超时与输出截断；高风险经确认门）。

    ``env_snapshot``：缺省方言与壳可得性；``None`` ⇒ 每次调用时 ``probe_environment()``。
    """

    def _snap() -> EnvironmentSnapshot:
        if env_snapshot is None:
            return probe_environment()
        if callable(env_snapshot):
            return env_snapshot()
        return env_snapshot

    async def handler(
        script: str,
        type: str | None = None,
        timeout: float = 10.0,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        snap = _snap()
        run_type = resolve_run_type(type, snap)
        child_env: dict[str, str] | None = None
        if run_type == "python":
            cmd = [sys.executable, "-c", script]
            child_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        else:
            if run_type == "powershell":
                script = f"{_PS_UTF8_PREAMBLE}\n{script}"
            cmd = shell_argv(run_type, script, snap)
        run_cwd = str(Path(cwd).expanduser()) if cwd else cwd
        proc = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=run_cwd,
            check=False,
            env=child_env,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        return {
            "type": run_type,
            "returncode": proc.returncode,
            "stdout": stdout[:_MAX_OUTPUT_CHARS],
            "stderr": stderr[:_MAX_OUTPUT_CHARS],
            "stdout_truncated": len(stdout) > _MAX_OUTPUT_CHARS,
            "stderr_truncated": len(stderr) > _MAX_OUTPUT_CHARS,
        }

    return Tool(
        definition=ToolDef(
            tool_id="tools.code_run",
            description=(
                "执行代码片段（python / bash / powershell），返回返回码与输出；"
                "显式 type 优先；未指定时 Windows 缺省 powershell、Darwin/Linux 缺省 bash；"
                "每次调用为全新进程（cd/环境变量不保留），目录用 cwd（支持 ~）；"
                "不可逆高风险，需审批"
            ),
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


def context_read(*, fetch_detail: Callable[[str], str]) -> Tool:
    """按信息地图指针取片段详情（只读，自动放行）——「模型按需跳转获取细节」的消费面。

    取详情**委托注入的取数器**（组合根传入装配器的 ``fetch_detail``）：本层不依赖
    context 层，与 ``gate_run`` 的执行器注入同理（context spec「信息地图」）。
    """
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {"pointer": {"type": "string"}},
        "required": ["pointer"],
    }

    def handler(pointer: str) -> dict[str, Any]:
        return {"pointer": pointer, "detail": fetch_detail(pointer)}

    return Tool(
        definition=ToolDef(
            tool_id="tools.context_read",
            description="按信息地图指针（doc_id#section）取文档片段详情，避免加载全文",
            schema=schema,
            coeffects=[],
            reversible=True,
        ),
        handler=handler,
    )


class GateOutcome(Protocol):
    """门禁结果的最小结构面（L1 视角）。

    只要求 ``passed`` / ``reason`` 两个属性，交付流水线的 ``GateResult`` 与之**结构兼容**
    —— 本层因此无需依赖 L5 的模型，执行器由组合根注入。
    """

    passed: bool
    reason: str


def gate_run(*, gates: tuple[str, ...], run_gate: Callable[[str], GateOutcome]) -> Tool:
    """按名触发质量门禁（执行器**注入**；不可逆高风险，经确认门）。

    门禁名与门禁命令取自交付流水线的**单一真源**（``GATE_COMMANDS``）：本层只做
    「白名单路由 + 结构化返回」，**不另立门禁命令、不依赖交付流水线层**。
    ``constraints.Validator`` 不校验 schema 的 ``enum`` ⇒ 白名单在处理器内**自行 fail-closed**。
    """
    allowed = tuple(gates)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {"gate": {"type": "string", "enum": list(allowed)}},
        "required": ["gate"],
    }

    async def handler(gate: str) -> dict[str, Any]:
        if gate not in allowed:
            # 白名单外 fail-closed：不触达执行器（结构化归一为 EXECUTION_FAILED）
            raise ValueError(f"未知门禁: {gate}（可选: {', '.join(allowed)}）")  # noqa: TRY003
        outcome = await asyncio.to_thread(run_gate, gate)
        return {"gate": gate, "passed": bool(outcome.passed), "reason": outcome.reason}

    return Tool(
        definition=ToolDef(
            tool_id="tools.gate_run",
            description="按名运行质量门禁，返回是否通过与否决原因；不可逆高风险，需审批",
            schema=schema,
            coeffects=["process:spawn", "filesystem:write"],
            reversible=False,
            timeout_s=660.0,  # 须大于执行器内部 600s 上界（否则工具层先于门禁自身超时）
        ),
        handler=handler,
    )


def builtin_tools() -> tuple[Tool, ...]:
    """零注入的内置原子工具集（**单一真源**）：组合根注册与只读诊断面计数共用一份。

    只含**无需注入**的五件（`file_read` / `file_write` / `file_patch` / `code_run` / `web_fetch`）；
    `gate_run` / `context_read` 的执行器由组合根注入，故由 `runtime` 另行装配。
    """
    return (file_read(), file_write(), file_patch(), code_run(), web_fetch())


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
