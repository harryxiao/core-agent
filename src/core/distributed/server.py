"""A2A Server（distributed）。

作为 Server 对外暴露能力被外部 Agent 调用：签发 AgentCard、接收任务（幂等去重）、
执行并回报结果。执行内部经 MCP 调用底层工具（注入 tool_caller）。

对应接口：doc/03-interfaces/distributed-interface.md §2
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .errors import DistributedError, DistributedErrorCode
from .models import AgentCard, Task, TaskHandle


class A2AServer:
    """A2A 服务端：暴露能力 + 接收执行任务。"""

    def __init__(
        self,
        *,
        card: AgentCard | None = None,
        signer: Callable[[bytes], str] | None = None,
        tool_caller: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> None:
        self._card = card
        self._signer = signer
        self._tool_caller: Callable[[str, dict[str, Any]], Any] = (
            tool_caller if tool_caller is not None else lambda _target, _payload: None
        )
        self._handles: dict[str, TaskHandle] = {}
        self._tasks: dict[str, Task] = {}

    def expose(self) -> AgentCard:
        """对外暴露（并签发）AgentCard。"""
        if self._card is None:
            raise DistributedError(
                DistributedErrorCode.A2A_CARD_INVALID,
                "未配置 AgentCard，无法对外暴露",
            )
        if self._signer is not None and self._card.signature is None:
            self._card.sign(self._signer)
        return self._card

    def on_message(self, task: Task) -> TaskHandle:
        """接收任务：按任务 ID 幂等去重，同一任务不重复执行。"""
        existing = self._handles.get(task.task_id)
        if existing is not None:
            return existing
        handle = TaskHandle(task_id=task.task_id, peer=task.target, status="pending")
        self._handles[task.task_id] = handle
        self._tasks[task.task_id] = task
        return handle

    def report(self, handle: TaskHandle) -> None:
        """执行任务并回报结果（内部经 MCP 调用底层工具）。"""
        task = self._tasks.get(handle.task_id)
        if task is None:
            raise DistributedError(
                DistributedErrorCode.A2A_TASK_FAILED,
                f"任务 {handle.task_id} 不存在",
            )
        handle.status = "running"
        try:
            handle.result = self._tool_caller(task.target, task.payload)
        except Exception as exc:  # noqa: BLE001 — 底层工具异常统一归为任务失败
            handle.status = "failed"
            raise DistributedError(
                DistributedErrorCode.A2A_TASK_FAILED,
                f"任务 {handle.task_id} 执行失败",
            ) from exc
        handle.status = "done"
