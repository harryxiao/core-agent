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
import contextlib
import math
import os
import stat
import subprocess
import sys
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from . import execution
from .env_shell import (
    EnvironmentSnapshot,
    probe_environment,
    resolve_run_type,
    shell_argv,
)
from .execution import ProcessRegistry
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
        "timeout": {
            "type": "number",
            "description": "超时秒数（缺省 120；允许 (0, 600]；后台任务不适用）",
        },
        "cwd": {
            "type": "string",
            "description": "工作目录（绝对路径；支持 ~ 展开；每次调用独立）",
        },
        "background": {
            "type": "boolean",
            "description": "true=后台执行，立即返回 pid 与输出文件路径（缺省 false）",
        },
    },
    "required": ["script"],
}

_PROCESS_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["list", "status", "output"]},
        "pid": {"type": "integer"},
        "max_chars": {
            "type": "integer",
            "description": "output 动作的尾部长（缺省 8192，上限 65536）",
        },
    },
    "required": ["action"],
}

_PROCESS_KILL_SCHEMA = {
    "type": "object",
    "properties": {"pid": {"type": "integer"}},
    "required": ["pid"],
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
_DEFAULT_RUN_TIMEOUT = 120.0  # 前景脚本缺省超时
_MAX_RUN_TIMEOUT = 600.0  # 前景脚本硬上限（工具外层 660s 兜底不先触发）
_DEFAULT_PROCESS_OUTPUT_CHARS = 8192  # tools.process output 尾部缺省长
_MAX_PROCESS_OUTPUT_CHARS = 65536  # tools.process output 尾部上限
_USER_AGENT = "core-agent/0.1"


def _truncate_output(text: str, limit: int = _MAX_OUTPUT_CHARS) -> str:
    """超出上限时首尾保留：头部约 1/3、尾部其余，中间省略标记含省略字符数。

    错误结论通常在尾部，故尾部权重更高；总长不超过 ``limit``。
    """
    if len(text) <= limit:
        return text
    marker_guess = len(f"\n…[truncated {len(text)} chars]…\n")
    budget = max(0, limit - marker_guess)
    head = budget // 3
    tail = budget - head
    removed = len(text) - budget
    marker = f"\n…[truncated {removed} chars]…\n"
    return text[:head] + marker + (text[-tail:] if tail else "")


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


def _atomic_overwrite(target: Path, content: str) -> None:
    """原子覆盖：同目录临时文件 + ``fsync`` + ``os.replace``（change 0257 / ADR-0248）。

    并发读者只可能看到**完整旧内容**或**完整新内容**，不会读到空文件 / 半截内容。
    失败（含替换失败）⇒ 清理临时文件并原样抛出，目标逐字不变。
    """
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        if target.exists():
            # 临时文件按 umask 新建；替换既有文件须**保留其权限位**
            os.chmod(tmp, stat.S_IMODE(target.stat().st_mode))
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


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
        if normalized == "w":
            _atomic_overwrite(target, content)
        else:
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


def _validate_timeout(timeout: float, background: bool) -> None:
    """前景 timeout 须为 (0, 硬上限] 内的有限秒数；后台不适用。"""
    if background:
        return
    if not math.isfinite(timeout) or not 0 < timeout <= _MAX_RUN_TIMEOUT:
        raise ValueError(  # noqa: TRY003 — 结构化错误消息由 Provider 归一
            f"timeout 须为 (0, {_MAX_RUN_TIMEOUT:g}] 内的秒数，收到: {timeout!r}"
        )


def _start_background(
    jobs: ProcessRegistry,
    cmd: list[str],
    cwd: str | None,
    env: dict[str, str] | None,
    run_type: str,
) -> dict[str, Any]:
    """后台启动并登记；注册表满 ⇒ 终止刚启动的任务、清理日志后拒绝。"""
    job = execution.spawn_background(cmd, cwd=cwd, env=env, run_type=run_type)
    try:
        jobs.add(job)
    except RuntimeError:
        execution.kill_process_tree(job.proc)
        with contextlib.suppress(OSError):
            job.output_path.unlink(missing_ok=True)
        raise
    return {
        "type": run_type,
        "background": True,
        "pid": job.pid,
        "output_path": str(job.output_path),
        "started_at": job.started_at,
    }


def code_run(
    *,
    env_snapshot: EnvironmentSnapshot | Callable[[], EnvironmentSnapshot] | None = None,
    registry: ProcessRegistry | None = None,
) -> Tool:
    """执行代码片段（python / bash / powershell；超时与输出截断；高风险经确认门）。

    ``env_snapshot``：缺省方言与壳可得性；``None`` ⇒ 每次调用时 ``probe_environment()``。
    ``registry``：后台任务注册表；``builtin_tools`` 注入**同一份**给进程管理工具，
    独立构造时自建（该实例的后台任务对别的工具面不可见）。
    """

    jobs = registry if registry is not None else ProcessRegistry()

    def _snap() -> EnvironmentSnapshot:
        if env_snapshot is None:
            return probe_environment()
        if callable(env_snapshot):
            return env_snapshot()
        return env_snapshot

    async def handler(
        script: str,
        type: str | None = None,
        timeout: float = _DEFAULT_RUN_TIMEOUT,
        cwd: str | None = None,
        background: bool = False,
    ) -> dict[str, Any]:
        _validate_timeout(timeout, background)
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
        if background:
            return _start_background(jobs, cmd, run_cwd, child_env, run_type)
        result = await execution.run_foreground(cmd, timeout=timeout, cwd=run_cwd, env=child_env)
        return {
            "type": run_type,
            "returncode": result.returncode,
            "stdout": _truncate_output(result.stdout),
            "stderr": _truncate_output(result.stderr),
            "stdout_truncated": len(result.stdout) > _MAX_OUTPUT_CHARS,
            "stderr_truncated": len(result.stderr) > _MAX_OUTPUT_CHARS,
        }

    return Tool(
        definition=ToolDef(
            tool_id="tools.code_run",
            description=(
                "执行代码片段（python / bash / powershell），返回返回码与输出；"
                "显式 type 优先；未指定时 Windows 缺省 powershell、Darwin/Linux 缺省 bash；"
                "每次调用为全新进程（cd/环境变量不保留），目录用 cwd（支持 ~）；"
                "background=true 时立即返回 pid 与输出文件路径；"
                "不可逆高风险，需审批"
            ),
            schema=_RUN_SCHEMA,
            coeffects=["process:spawn", "filesystem:write"],
            reversible=False,
            timeout_s=660.0,  # > 脚本内层硬上限 600s；外层只作兜底
        ),
        handler=handler,
    )


def _tail_text(path: Path, limit: int) -> str:
    """读文件尾部（UTF-8 按最坏 4 字节/字符有界读取，非法字节替换）。"""
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - limit * 4))
        raw = fh.read()
    return raw.decode("utf-8", errors="replace")[-limit:]


def process_manage(*, registry: ProcessRegistry) -> Tool:
    """后台任务巡检（list / status / output，只读，自动放行）。"""

    def handler(
        action: str,
        pid: int | None = None,
        max_chars: int = _DEFAULT_PROCESS_OUTPUT_CHARS,
    ) -> dict[str, Any]:
        if action == "list":
            return {"jobs": [job.info() for job in registry.list()]}
        if action not in ("status", "output"):
            raise ValueError(f"未知动作: {action}（可选: list/status/output）")  # noqa: TRY003
        if pid is None:
            raise ValueError(f"action={action} 需要 pid")  # noqa: TRY003
        job = registry.get(pid)
        if job is None:
            return {"pid": pid, "found": False}
        if action == "status":
            return {"found": True, **job.info()}
        if not 0 < max_chars <= _MAX_PROCESS_OUTPUT_CHARS:
            raise ValueError(  # noqa: TRY003 — 结构化错误消息由 Provider 归一
                f"max_chars 须为 (0, {_MAX_PROCESS_OUTPUT_CHARS}]，收到: {max_chars}"
            )
        return {"found": True, **job.info(), "output": _tail_text(job.output_path, max_chars)}

    return Tool(
        definition=ToolDef(
            tool_id="tools.process",
            description="后台任务巡检：list / status / output（只读，自动放行）",
            schema=_PROCESS_SCHEMA,
            coeffects=["process:read"],
            reversible=True,
            timeout_s=10.0,
        ),
        handler=handler,
    )


def _kill_job(registry: ProcessRegistry, pid: int) -> dict[str, Any]:
    job = registry.get(pid)
    if job is None:
        return {"pid": pid, "found": False, "killed": False}
    if job.proc is None:
        # 恢复项无进程句柄、身份无法在全部平台安全验证 ⇒ 只读，不触达进程
        return {"pid": pid, "found": True, "killed": False, "restored": True}
    already_exited = job.proc.poll() is not None
    if not already_exited:
        execution.kill_process_tree(job.proc)
    with contextlib.suppress(subprocess.TimeoutExpired):
        job.proc.wait(timeout=5)
    return {
        "pid": pid,
        "found": True,
        "killed": not already_exited,
        "returncode": job.proc.poll(),
    }


def process_kill(*, registry: ProcessRegistry) -> Tool:
    """终止注册表内的后台任务（不可逆写，经确认门；不接受任意 pid）。"""

    async def handler(pid: int) -> dict[str, Any]:
        return await asyncio.to_thread(_kill_job, registry, pid)

    return Tool(
        definition=ToolDef(
            tool_id="tools.process_kill",
            description="终止本进程启动的后台任务及其后代（仅注册表内 pid；不可逆，需审批）",
            schema=_PROCESS_KILL_SCHEMA,
            coeffects=["process:write"],
            reversible=False,
            timeout_s=30.0,
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


# 工具参数查询的固定 id（change 0272 / ADR-0262）：planner 的按需注入与 loop 的加载吸收
# 共用此单一真源（不得各写一份字面量）。
SCHEMA_READ_TOOL_ID = "tools.schema_read"


def schema_read(*, catalog: Callable[[], list[ToolDef]]) -> Tool:
    """按需查询工具参数 schema（只读，自动放行）——「工具目录常驻、参数按需加载」的消费面。

    目录**委托注入的取数器**（组合根传 ``tools.active_tools``）：本层不持有注册表，
    故返回内容始终反映调用时的真实工具面（含 MCP 动态工具）。参数 schema 放进工具观察，
    使文本 JSON 动作路径的模型也能读到（change 0272 / ADR-0262）。
    """
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "tool_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要加载参数 schema 的工具 id 列表；省略则列出全部可用工具",
            }
        },
    }

    def handler(tool_ids: list[str] | None = None) -> dict[str, Any]:
        defs = {definition.tool_id: definition for definition in catalog()}
        if not tool_ids:
            return {
                "tools": [
                    {"tool_id": tool_id, "description": definition.description}
                    for tool_id, definition in defs.items()
                ]
            }
        schemas: list[dict[str, Any]] = []
        unknown: list[str] = []
        for tool_id in tool_ids:
            definition = defs.get(tool_id)
            if definition is None:
                unknown.append(tool_id)
                continue
            schemas.append(
                {
                    "tool_id": tool_id,
                    "description": definition.description,
                    "parameters": definition.schema,
                }
            )
        return {"schemas": schemas, "unknown": unknown}

    return Tool(
        definition=ToolDef(
            tool_id=SCHEMA_READ_TOOL_ID,
            description=(
                "查询工具参数 schema（未随请求注入参数的工具，须先经本工具加载，下一轮生效）；"
                "不带参数列出全部可用工具"
            ),
            schema=schema,
            coeffects=["schema:read"],
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

    只含**无需注入**的七件（`file_read` / `file_write` / `file_patch` / `code_run` /
    `web_fetch` / `process` / `process_kill`）；`code_run` 与两个进程工具共享**同一份**
    后台任务注册表。`gate_run` / `context_read` 的执行器由组合根注入，故由 `runtime` 另行装配。
    """
    registry = ProcessRegistry()
    return (
        file_read(),
        file_write(),
        file_patch(),
        code_run(registry=registry),
        web_fetch(),
        process_manage(registry=registry),
        process_kill(registry=registry),
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
