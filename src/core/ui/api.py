"""统一后端 API 层（ui）。

三种启动模式（CLI/Web/Desktop）复用同一内核与同一 LLM 配置源，走同一套
API：会话 / 循环（SSE 流式）、记忆、工具、LLM 配置；CLI 的 Textual 层也不绕过。

对应接口：doc/03-interfaces/ui-interface.md §1
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

from core.configuration import ConfigManager
from core.configuration.models import LLMConfig
from core.loop import DefaultLoop, LoopEvent, LoopPlugin
from core.memory import MemoryStore
from core.orchestration import TaskScheduler
from core.permission import ApprovalChannel
from core.tools import ToolDef, ToolProvider, ToolResult

from .errors import UiError, UiErrorCode
from .models import Event

# LoopEvent 类型 → SSE 事件类型（DefaultLoop 产出七类 LoopEvent，spec：异步流式执行）。
_EVENT_MAP = {
    "loop_started": "session.created",
    "step_completed": "loop.action",  # 既有契约（回合推进），不随动作事件新增而改名
    "action_started": "loop.action_started",
    "action_completed": "loop.action_completed",
    "reply_delta": "loop.result",
    "loop_finished": "loop.result",
    "loop_failed": "loop.error",
}


class UIAPILayer:
    """统一后端 API：三模共用的会话 / 循环 / 记忆 / 工具 / LLM 配置入口。"""

    def __init__(  # noqa: PLR0913 — 注入面均为可选依赖注入
        self,
        *,
        loop: LoopPlugin | None = None,
        memory: MemoryStore | None = None,
        tools: ToolProvider | None = None,
        config: ConfigManager | None = None,
        supported_modalities: set[str] | None = None,
        approval: ApprovalChannel | None = None,
        orchestrator: TaskScheduler | None = None,
    ) -> None:
        self._loop = loop if loop is not None else DefaultLoop()
        self._memory = memory
        self._tools = tools if tools is not None else ToolProvider()
        self._config = config
        self._modalities: set[str] = (
            supported_modalities if supported_modalities is not None else set()
        )
        self._approval = approval
        self._orchestrator = orchestrator
        self._sessions: dict[str, str] = {}
        self._llm_config: LLMConfig | None = None

    @property
    def approval(self) -> ApprovalChannel | None:
        """交互审批通道（高风险工具 confirm 门的终端 y/n）；非交互入口为 None。"""
        return self._approval

    # ---- 会话与循环 ----

    def create_session(self, mode: str) -> str:
        """新建会话，返回 session_id。"""
        session_id = uuid.uuid4().hex
        self._sessions[session_id] = mode
        return session_id

    async def run_loop(
        self,
        session_id: str,
        user_input: str,
        *,
        modalities: list[str] | None = None,
    ) -> AsyncIterator[Event]:
        """SSE 流式输出 loop 事件；会话不存在 / LLM key 未配 / 模态缺失分别报错。"""
        self._require_session(session_id)
        self._require_llm_key()
        for modality in modalities or []:
            if modality not in self._modalities:
                raise UiError(
                    UiErrorCode.UI_MODALITY_MISSING,
                    f"模型不具备 {modality} 模态理解能力",
                )
        stream = self._loop.astream(user_input, session_id=session_id)
        async for loop_event in cast(AsyncIterator[LoopEvent], stream):
            yield self._map_event(session_id, loop_event)

    async def run_task(self, session_id: str, goal: str) -> AsyncIterator[Event]:
        """SSE 流式输出编排任务进度事件（task.* 前缀）；进度事件与 CLI task 入口同构。"""
        self._require_session(session_id)
        if self._orchestrator is None:
            raise UiError(UiErrorCode.UI_ORCHESTRATOR_UNSET, "编排器未注入（任务入口不可用）")
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        async for task_event in self._orchestrator.astream(task_id, goal):
            yield Event(type=f"task.{task_event.type}", payload=task_event.payload)

    def barge_in(self) -> None:
        """语音播报被打断（barge-in）：语音输出为抽象能力（TTS 后端未接）。"""
        raise UiError(UiErrorCode.UI_BARGEIN, "语音播报被打断（barge-in）")

    # ---- 记忆 ----

    def get_memory(self, session_id: str) -> dict[str, object]:
        """返回会话记忆（只含归属该会话的条目；未归属/他会话条目不可见）。"""
        self._require_session(session_id)
        if self._memory is None:
            return {"entries": []}
        entries = self._memory.read(session_id, budget=2048)
        return {"entries": [e.content for e in entries if e.session_id == session_id]}

    def compact(self, session_id: str) -> None:
        """压缩会话记忆：触发存储层真实压实（按会话聚合摘要 + 重要度写回，可撤销）。"""
        self._require_session(session_id)
        if self._memory is not None:
            self._memory.compact(session_id)

    # ---- 工具 ----

    def list_tools(self) -> list[ToolDef]:
        """返回已注册工具定义列表（经 ToolProvider）。"""
        return self._tools.active_tools()

    def invoke_tool(self, tool_id: str, args: dict[str, Any]) -> ToolResult:
        """同步调用工具，结果经 ToolResult 承载。"""
        return self._tools.invoke(tool_id, args, trace_id=uuid.uuid4().hex)

    # ---- LLM 配置（三模唯一配置源） ----

    def get_llm_config(self) -> LLMConfig:
        """返回当前 LLM 配置（api_key 为 ${VAR} 引用，非明文）。"""
        return self._require_llm_key()

    def set_llm_config(self, cfg: LLMConfig) -> None:
        """热更新 LLM 配置；api_key 只接受 ${VAR} 引用，拒绝明文。"""
        if cfg.api_key_ref and not (
            cfg.api_key_ref.startswith("${") and cfg.api_key_ref.endswith("}")
        ):
            raise UiError(UiErrorCode.UI_LLM_KEY_UNSET, "API key 必须为 ${VAR} 引用，禁止明文")
        self._llm_config = cfg

    # ---- 内部辅助 ----

    def _require_session(self, session_id: str) -> None:
        if session_id not in self._sessions:
            raise UiError(UiErrorCode.UI_SESSION_NOT_FOUND, f"会话 {session_id} 不存在")

    def _require_llm_key(self) -> LLMConfig:
        cfg = self._llm_config
        if cfg is None or not cfg.api_key_ref:
            raise UiError(UiErrorCode.UI_LLM_KEY_UNSET, "LLM API Key 未配置")
        return cfg

    @staticmethod
    def _map_event(session_id: str, loop_event: LoopEvent) -> Event:
        event_type = _EVENT_MAP.get(loop_event.type, loop_event.type)
        if loop_event.type == "loop_started":
            base: dict[str, object] = (
                cast(dict[str, object], loop_event.payload) if loop_event.payload else {}
            )
            payload: object = {"session_id": session_id, **base}
        else:
            payload = loop_event.payload
        return Event(type=event_type, payload=payload)
