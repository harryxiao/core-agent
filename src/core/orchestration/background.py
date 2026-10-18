"""后台子 Agent 注册表与完成通知（change 0270 / ADR-0260）。

`tools.delegate(background=true)` 立即返回 `task_id`；子 Agent 在事件循环上后台执行，
完成后按**会话**记一条待投递通知，由该会话下一轮轮首一次性取走（loop 的
`notices_consult` 注入点）。`tools.tasks` 提供只读清单，查询**不**清空通知。

与 `core.tools.execution.ProcessRegistry` 的区别：本注册表管理的是**子 Agent 的 loop**，
不是 OS 进程；语义归编排层（L3.5），不塞进 L1 工具实现。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import math
import os
import time
import uuid
import warnings
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from core.loop import LoopPlugin
from core.memory.extract import redact_secrets
from core.tools import Tool, ToolDef

from .errors import OrchestrationError, OrchestrationErrorCode
from .models import AgentProfile

DEFAULT_MAX_RUNNING = 8
DEFAULT_NOTICE_CAP = 32

_NOTICE_LINES = 10
_NOTICE_LINE_CHARS = 400
_TASK_TEXT_CHARS = 120
_REPLY_PREVIEW_CHARS = 200
_REPLY_STORE_CHARS = 4000

# 跨重启登记（change 0279 / ADR-0269）：条目有界、错误文本有界。
_MAX_PERSISTED = 64
_PERSIST_VERSION = 1
_ERROR_CHARS = 200
_INTERRUPTED_ERROR = "进程重启导致中断"
_STATUSES = frozenset({"running", "done", "failed", "cancelled", "interrupted"})

TASKS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["list", "status"],
            "description": "list = 全部后台任务；status = 单个任务",
        },
        "task_id": {"type": "string", "description": "action=status 时必填"},
    },
    "required": ["action"],
}

TASK_RETRY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "task_id": {
            "type": "string",
            "description": "要重入队的后台任务 id（interrupted / failed / cancelled）",
        },
    },
    "required": ["task_id"],
}


@dataclass
class BackgroundTaskInfo:
    """一条后台委托任务的运行状态（值均有界）。"""

    task_id: str
    agent_id: str
    task: str
    status: str = "running"  # running / done / failed / cancelled
    started_at: float = 0.0
    finished_at: float | None = None
    reply: str = ""
    error: str = ""
    session_id: str = field(default="", repr=False)

    def info(self) -> dict[str, Any]:
        """对模型暴露的只读快照（不含会话标识；文本均有界）。"""
        return {
            "task_id": self.task_id,
            "agent": self.agent_id,
            "task": self.task[:_TASK_TEXT_CHARS],
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "reply": self.reply[:_REPLY_STORE_CHARS],
            "error": self.error,
        }


def render_notice_lines(tasks: list[BackgroundTaskInfo]) -> str:
    """完成通知渲染：每任务一行、单行 ≤400 字符、最多最近 10 条。"""
    lines: list[str] = []
    for info in tasks[-_NOTICE_LINES:]:
        outcome = info.reply[:_REPLY_PREVIEW_CHARS] or info.error or "（无）"
        line = (
            f"- [{info.status}] {info.task_id}（{info.agent_id}）"
            f"任务：{info.task[:_TASK_TEXT_CHARS]}；结果：{outcome}"
        )
        lines.append(line[:_NOTICE_LINE_CHARS])
    return "\n".join(lines)


def _info_record(info: BackgroundTaskInfo) -> dict[str, Any]:
    """可持久化元数据：任务正文与错误经脱敏并有界；**不**落回复正文（change 0279）。"""
    return {
        "task_id": info.task_id,
        "agent_id": info.agent_id,
        "task": redact_secrets(info.task)[:_TASK_TEXT_CHARS],
        "status": info.status,
        "started_at": info.started_at,
        "finished_at": info.finished_at,
        "session_id": info.session_id,
        "error": redact_secrets(info.error)[:_ERROR_CHARS],
    }


def _restore_info(item: object) -> BackgroundTaskInfo | None:  # noqa: PLR0911 — 逐字段校验多早退
    """校验并恢复一条登记；非法条目跳过（不抛错）；``running`` 映射为 ``interrupted``。"""
    if not isinstance(item, dict):
        return None
    record = cast(dict[str, Any], item)
    task_id = record.get("task_id")
    agent_id = record.get("agent_id")
    task = record.get("task")
    status = record.get("status")
    started_at = record.get("started_at")
    finished_at = record.get("finished_at")
    session_id = record.get("session_id", "")
    error = record.get("error", "")
    if not isinstance(task_id, str) or not task_id:
        return None
    if not isinstance(agent_id, str) or not agent_id:
        return None
    if not isinstance(task, str) or not isinstance(status, str) or status not in _STATUSES:
        return None
    if (
        not isinstance(started_at, (int, float))
        or isinstance(started_at, bool)
        or not math.isfinite(started_at)
    ):
        return None
    if finished_at is not None and (
        not isinstance(finished_at, (int, float))
        or isinstance(finished_at, bool)
        or not math.isfinite(finished_at)
    ):
        return None
    if not isinstance(session_id, str) or not isinstance(error, str):
        return None
    if status == "running":  # 进程已不在此处 ⇒ 在途任务按被中断处理（不重放通知）
        status = "interrupted"
        finished_at = None
        error = _INTERRUPTED_ERROR
    return BackgroundTaskInfo(
        task_id=task_id,
        agent_id=agent_id,
        # 读侧同样脱敏：旧格式 / 手工编辑的文件也不得把密钥形态正文重新带进内存。
        task=redact_secrets(task)[:_TASK_TEXT_CHARS],
        status=status,
        started_at=float(started_at),
        finished_at=float(finished_at) if finished_at is not None else None,
        error=redact_secrets(error)[:_ERROR_CHARS],
        session_id=session_id,
    )


class BackgroundAgentRegistry:
    """有界的后台委托注册表：spawn 立即返回，终态不可变，通知按会话堆积。

    ``state_path`` 非空时元数据跨重启登记（change 0279 / ADR-0269）：写入 0600 原子替换，
    最多保留最新 ``max_records`` 条；加载时把落盘的 ``running`` 映射为 ``interrupted``。
    缺省 ``None`` ⇒ 纯内存（既有构造零变化）。
    """

    def __init__(
        self,
        state_path: Path | str | None = None,
        *,
        max_running: int = DEFAULT_MAX_RUNNING,
        notice_cap: int = DEFAULT_NOTICE_CAP,
        max_records: int = _MAX_PERSISTED,
    ) -> None:
        self._path = Path(state_path) if state_path is not None else None
        self._max_running = max_running
        self._notice_cap = notice_cap
        self._max_records = max_records
        self._infos: dict[str, BackgroundTaskInfo] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._notices: dict[str, deque[BackgroundTaskInfo]] = {}
        self._warned_persist = False
        if self._path is not None:
            self._load()

    @property
    def notice_cap(self) -> int:
        return self._notice_cap

    def running_count(self) -> int:
        return sum(1 for info in self._infos.values() if info.status == "running")

    def spawn(
        self,
        loop: LoopPlugin,
        task: str,
        *,
        agent_id: str,
        session_id: str = "",
    ) -> str:
        """起一个后台委托并**立即**返回 task_id；超限抛 `BACKGROUND_TASKS_FULL`。"""
        if self.running_count() >= self._max_running:
            raise OrchestrationError(
                OrchestrationErrorCode.BACKGROUND_TASKS_FULL,
                f"后台任务已达上限 {self._max_running}",
            )
        task_id = f"bg-{uuid.uuid4().hex[:12]}"
        info = BackgroundTaskInfo(
            task_id=task_id,
            agent_id=agent_id,
            task=task,
            started_at=time.time(),
            session_id=session_id,
        )
        self._infos[task_id] = info
        running = asyncio.create_task(self._run(loop, task, session_id))
        self._tasks[task_id] = running
        running.add_done_callback(lambda done: self._finalize(task_id, done))
        self._save()
        return task_id

    def get(self, task_id: str) -> BackgroundTaskInfo | None:
        return self._infos.get(task_id)

    def list(self) -> list[BackgroundTaskInfo]:
        """全部任务（按发起顺序）。"""
        return list(self._infos.values())

    def drain_notices(self, session_id: str) -> list[BackgroundTaskInfo]:
        """取走该会话的待投递通知（一次性）；其他会话不受影响。"""
        queue = self._notices.pop(session_id, None)
        return list(queue) if queue is not None else []

    def render_notices(self, session_id: str) -> str:
        """取走并渲染该会话的待投递通知（供 loop 的 `notices_consult`）。"""
        return render_notice_lines(self.drain_notices(session_id))

    def cancel(self, task_id: str) -> bool:
        """请求取消并**同步**落 cancelled 终态（回调随后看到终态即跳过）。"""
        task = self._tasks.get(task_id)
        if task is None or task.done():
            return False
        info = self._infos.get(task_id)
        if info is not None:
            self._mark_terminal(info, status="cancelled")
        task.cancel()
        return True

    def cancel_all(self) -> None:
        for task_id in list(self._tasks):
            self.cancel(task_id)

    async def wait(self, task_id: str) -> BackgroundTaskInfo:
        """等待任务落终态（测试 / 收尾用）；取消与异常都不抛，返回终态快照。"""
        info = self._infos.get(task_id)
        if info is None:
            raise KeyError(task_id)
        task = self._tasks.get(task_id)
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            # 任务完成回调可能尚未被事件循环执行；此处兜底（幂等）。
            self._finalize(task_id, task)
        return info

    # ---- 内部 ----

    async def _run(self, loop: LoopPlugin, task: str, session_id: str) -> Any:
        return await loop.arun(task, session_id=session_id)

    def _finalize(self, task_id: str, task: asyncio.Task[Any]) -> None:
        """落终态 + 记通知（幂等；取消也留痕）。"""
        info = self._infos.get(task_id)
        self._tasks.pop(task_id, None)
        if info is None or info.status != "running":
            return
        if task.cancelled():
            self._mark_terminal(info, status="cancelled")
            return
        error = task.exception()
        if error is not None:
            self._mark_terminal(info, status="failed", error=type(error).__name__)
            return
        result = task.result()
        failed = bool(getattr(result, "failed", False))
        self._mark_terminal(
            info,
            status="failed" if failed else "done",
            reply=str(getattr(result, "reply", "")),
            error="子 Agent 报告失败" if failed else "",
        )

    def _mark_terminal(
        self,
        info: BackgroundTaskInfo,
        *,
        status: str,
        reply: str = "",
        error: str = "",
    ) -> None:
        """不可逆落终态并追加一条待投递通知（重复调用无副作用）。"""
        if info.status != "running":
            return
        info.status = status
        info.reply = reply[:_REPLY_STORE_CHARS]
        info.error = error
        info.finished_at = time.time()
        found: deque[BackgroundTaskInfo] | None = self._notices.get(info.session_id)
        if found is None:
            found = deque(maxlen=self._notice_cap)
            self._notices[info.session_id] = found
        queue: deque[BackgroundTaskInfo] = found
        queue.append(info)
        self._save()

    # ---- 跨重启登记（change 0279 / ADR-0269） ----

    def _load(self) -> None:
        """加载登记文件：缺失 ⇒ 空；损坏 ⇒ 告警并空；``running`` ⇒ ``interrupted``。"""
        path = self._path
        if path is None:
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            self._warn_corrupt()
            return
        if not isinstance(raw, dict):
            self._warn_corrupt()
            return
        items = cast(dict[str, Any], raw).get("tasks")
        if not isinstance(items, list):
            self._warn_corrupt()
            return
        restored = [
            info for item in cast(list[Any], items) if (info := _restore_info(item)) is not None
        ]
        restored.sort(key=lambda info: info.started_at)
        for info in restored[-self._max_records :]:
            self._infos[info.task_id] = info

    def _save(self) -> None:
        """整体重写登记文件：同目录临时文件 + fsync + 原子替换（失败告警一次）。"""
        path = self._path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            newest = sorted(self._infos.values(), key=lambda info: info.started_at)
            payload = {
                "version": _PERSIST_VERSION,
                "tasks": [_info_record(info) for info in newest[-self._max_records :]],
            }
            tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, path)
            except BaseException:
                with contextlib.suppress(OSError):
                    tmp.unlink(missing_ok=True)
                raise
        except OSError:
            self._warn_persist()

    def _warn_corrupt(self) -> None:
        assert self._path is not None
        warnings.warn(
            f"后台任务登记文件损坏，按空登记处理: {self._path.name}",
            stacklevel=3,
        )

    def _warn_persist(self) -> None:
        if self._warned_persist:
            return
        self._warned_persist = True
        name = self._path.name if self._path is not None else ""
        warnings.warn(f"后台任务登记无法落盘（仅本进程内有效）: {name}", stacklevel=2)


def background_tasks_tool(*, registry: BackgroundAgentRegistry) -> Tool:
    """模型侧任务清单（list / status，只读，自动放行）。"""

    def handler(action: str, task_id: str | None = None) -> dict[str, Any]:
        if action == "list":
            return {"tasks": [info.info() for info in registry.list()]}
        if action != "status":
            raise ValueError(f"未知动作: {action}（可选: list/status）")  # noqa: TRY003
        if not task_id:
            raise ValueError("action=status 需要 task_id")  # noqa: TRY003
        info = registry.get(task_id)
        if info is None:
            return {"task_id": task_id, "found": False}
        return {"found": True, **info.info()}

    return Tool(
        definition=ToolDef(
            tool_id="tools.tasks",
            description="后台子 Agent 任务清单：list / status（只读，自动放行）",
            schema=TASKS_SCHEMA,
            coeffects=["task:read"],
            reversible=True,
            timeout_s=10.0,
        ),
        handler=handler,
    )


def task_retry_tool(
    *, registry: BackgroundAgentRegistry, match: Callable[[str], AgentProfile]
) -> Tool:
    """重入队工具：按登记的任务正文重新路由并启动新后台任务（需审批）。"""

    def handler(task_id: str) -> dict[str, Any]:  # noqa: PLR0911 — 逐种拒绝原因早退
        info = registry.get(task_id)
        if info is None:
            return {"ok": False, "error": f"未登记的后台任务: {task_id}"}
        if info.status == "running":
            return {"ok": False, "error": f"任务仍在运行，无需重入队: {task_id}"}
        if info.status == "done":
            return {"ok": False, "error": f"任务已完成，不自动重入队: {task_id}"}
        try:
            profile = match(info.task)
        except OrchestrationError as exc:
            return {"ok": False, "error": f"无匹配子 Agent: {exc}"}
        if profile.loop is None:
            return {"ok": False, "error": f"子 Agent {profile.agent_id} 无可用 loop"}
        try:
            new_id = registry.spawn(
                profile.loop,
                info.task,
                agent_id=profile.agent_id,
                session_id=info.session_id,
            )
        except OrchestrationError as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "task_id": new_id,
            "status": "running",
            "agent": profile.agent_id,
            "retried": task_id,
        }

    return Tool(
        definition=ToolDef(
            tool_id="tools.task_retry",
            description=(
                "重入队被中断 / 失败 / 取消的后台子 Agent 任务（需审批）；"
                "按原任务正文重新路由并返回新 task_id"
            ),
            schema=TASK_RETRY_SCHEMA,
            coeffects=["task:write"],
            reversible=False,
            timeout_s=10.0,
        ),
        handler=handler,
    )
