"""统一后端 API 层（ui）。

三种启动模式（CLI/Web/Desktop）复用同一内核与同一 LLM 配置源，走同一套
API：会话 / 循环（SSE 流式）、记忆、工具、LLM 配置；CLI 的 Textual 层也不绕过。

对应接口：doc/03-interfaces/ui-interface.md §1
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

from core.configuration import ConfigManager, ConfigurationError
from core.configuration.models import LLMConfig
from core.loop import DefaultLoop, LimitsConfigurable, LoopEvent, LoopPlugin
from core.memory import MemoryStore
from core.orchestration import TaskScheduler
from core.permission import ApprovalChannel
from core.pet.core import PetActivator, PetControl
from core.tools import ToolDef, ToolProvider, ToolResult

from .errors import UiError, UiErrorCode
from .models import Event
from .sessions import SessionRegistry

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


# 输出预留缺省口径来源：doc/openspec/specs/configuration/spec.md「循环预算配置」。
# 仅在**无配置源**（裸 UIAPILayer）时就地派生；有配置源一律以 ConfigManager.loop_limits() 为准。
_DEFAULT_OUTPUT_RESERVE = 8192


def _require_ref(ref: str) -> None:
    """非空且非 ``${VAR}`` 引用 ⇒ 拒绝明文密钥（口径不因入口不同而松动）。"""
    if ref and not (ref.startswith("${") and ref.endswith("}")):
        raise UiError(UiErrorCode.UI_LLM_KEY_UNSET, "API key 必须为 ${VAR} 引用，禁止明文")


def _llm_patch(
    cfg: LLMConfig, *, output_reserve: int | None, max_rounds: int | None
) -> dict[str, Any]:
    """组**单个** patch（llm + loop）⇒ 一次校验、一次落盘，无「写了一半」的中间态。"""
    patch: dict[str, Any] = {
        "llm": {
            "api_key": cfg.api_key_ref,
            "provider": cfg.provider,
            "model": cfg.model,
            "endpoint": cfg.endpoint,
            "reasoning_effort": cfg.reasoning_effort,
            "embedding_model": cfg.embedding_model,
            "context_window": cfg.context_window,
        }
    }
    loop: dict[str, Any] = {}
    if output_reserve is not None:
        loop["output_reserve"] = output_reserve
    if max_rounds is not None:
        loop["max_rounds"] = max_rounds
    if loop:
        patch["loop"] = loop
    return patch


def _derive_budget(cfg: LLMConfig, output_reserve: int | None) -> int | None:
    """无配置源时的预算派生；``None`` = 未配窗口 ⇒ 保持 loop 现有预算。"""
    if cfg.context_window <= 0:
        return None
    budget = cfg.context_window - (
        _DEFAULT_OUTPUT_RESERVE if output_reserve is None else output_reserve
    )
    if budget <= 0:
        raise UiError(UiErrorCode.UI_LLM_CONFIG_INVALID, "上下文窗口不敷输出预留")
    return budget


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
        pet_activator: PetActivator | None = None,
        pet_control: PetControl | None = None,
        registry: SessionRegistry | None = None,
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
        self._pet_activator = pet_activator
        self._pet_control = pet_control
        self._registry = registry if registry is not None else SessionRegistry()
        self._llm_config: LLMConfig | None = None

    @property
    def approval(self) -> ApprovalChannel | None:
        """交互审批通道（高风险工具 confirm 门的终端 y/n）；非交互入口为 None。"""
        return self._approval

    # ---- 会话与循环 ----

    def create_session(self, mode: str) -> str:
        """新建会话，返回 session_id（经注册表登记，落盘注册表则跨进程可见）。"""
        return self._registry.create(mode)

    def list_sessions(self) -> list[dict[str, object]]:
        """枚举已登记对话会话（`{session_id, mode, created_at}`）。"""
        return self._registry.list()

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
        async for task_event in self._orchestrator.astream(task_id, goal, session_id=session_id):
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

    # ---- 宠物（WebUI 自然语言入口） ----

    def activate_pet(self, user_input: str) -> str:
        """WebUI 自然语言「启动宠物 + 任务」入口；返回已激活宠物会话 id。"""
        if self._pet_activator is None:
            raise UiError(UiErrorCode.UI_PET_UNSET, "宠物激活器未接")
        return self._pet_activator.activate_from_nl(user_input).session_id

    def pet_command(
        self, verb: str, *, session_id: str | None = None, goal: str | None = None
    ) -> Any:
        """前台 `/pet [cmd]` 控制面（change 0088 / 用户诉求①）：verb → 会话操作。

        `status` / `result` / `sleep` / `wake` / `assign` / `stop` 经注入的 `PetControl` 收口
        （与 CLI 同一实现）。
        """
        if self._pet_control is None:
            raise UiError(UiErrorCode.UI_PET_UNSET, "宠物控制面未接")
        if verb == "status":
            return self._pet_control.status(session_id)
        if verb == "result":
            return self._pet_control.result(session_id)
        if verb == "sleep":
            return self._pet_control.sleep(session_id)
        if verb == "wake":
            return self._pet_control.wake(session_id)
        if verb == "assign":
            return self._pet_control.assign(goal or "", session_id=session_id)
        if verb == "stop":
            return self._pet_control.stop(session_id)
        raise UiError(UiErrorCode.UI_PET_UNKNOWN_VERB, f"未知宠物控制动词：{verb}")

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
        """启动期 hydrate LLM 配置（纯内存）；api_key 只接受 ${VAR} 引用，拒绝明文。

        **不落盘**：本入口的值可能来自 env/CLI（yaml 里未必有），落盘等于每次启动重写
        config.yaml。用户显式保存走 ``apply_llm_config``。
        """
        _require_ref(cfg.api_key_ref)
        self._llm_config = cfg

    def apply_llm_config(
        self,
        cfg: LLMConfig,
        *,
        output_reserve: int | None = None,
        max_rounds: int | None = None,
    ) -> None:
        """用户保存 LLM 配置：校验 → 原子落盘 → 生效 → 热推预算上限（change `0099`）。

        有配置源时按 ``entry._config_set`` 范式（apply_change → write_patch → 重读）；无配置源
        （裸 ``UIAPILayer``）降级为纯内存 + 尽力热生效，不假装持久化。非法取值、落盘失败一律
        归为 ``UI_LLM_CONFIG_INVALID``，且**内存与 yaml 均回退到原值**。
        """
        _require_ref(cfg.api_key_ref)
        patch = _llm_patch(cfg, output_reserve=output_reserve, max_rounds=max_rounds)
        limits: tuple[int | None, int | None]
        if self._config is not None:
            try:
                self._config.apply_change(patch)
                self._config.write_patch(patch)
            except ConfigurationError as exc:
                raise UiError(UiErrorCode.UI_LLM_CONFIG_INVALID, str(exc)) from exc
            except OSError as exc:
                self._config.load()  # 原子写保证 yaml 仍是旧值 ⇒ 重读即回滚内存
                raise UiError(UiErrorCode.UI_LLM_CONFIG_INVALID, f"配置落盘失败：{exc}") from exc
            try:
                self._config.load()
            except ConfigurationError as exc:
                raise UiError(UiErrorCode.UI_LLM_CONFIG_INVALID, str(exc)) from exc
            limits = self._config.loop_limits()
        else:
            limits = (max_rounds, _derive_budget(cfg, output_reserve))

        self._llm_config = cfg
        if isinstance(self._loop, LimitsConfigurable):
            self._loop.set_limits(max_rounds=limits[0], token_budget=limits[1])

    def get_loop_limits(self) -> tuple[int, int] | None:
        """回显**生效值** ``(max_rounds, token_budget)``；无配置源返回 None。"""
        return None if self._config is None else self._config.loop_limits()

    # ---- 内部辅助 ----

    def _require_session(self, session_id: str) -> None:
        if not self._registry.exists(session_id):
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
