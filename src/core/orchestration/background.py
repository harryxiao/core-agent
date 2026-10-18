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
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from core.loop import LoopPlugin
from core.tools import Tool, ToolDef

from .errors import OrchestrationError, OrchestrationErrorCode

DEFAULT_MAX_RUNNING = 8
DEFAULT_NOTICE_CAP = 32

_NOTICE_LINES = 10
_NOTICE_LINE_CHARS = 400
_TASK_TEXT_CHARS = 120
_REPLY_PREVIEW_CHARS = 200
_REPLY_STORE_CHARS = 4000

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


class BackgroundAgentRegistry:
    """有界的后台委托注册表：spawn 立即返回，终态不可变，通知按会话堆积。"""

    def __init__(
        self,
        *,
        max_running: int = DEFAULT_MAX_RUNNING,
        notice_cap: int = DEFAULT_NOTICE_CAP,
    ) -> None:
        self._max_running = max_running
        self._notice_cap = notice_cap
        self._infos: dict[str, BackgroundTaskInfo] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._notices: dict[str, deque[BackgroundTaskInfo]] = {}

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
