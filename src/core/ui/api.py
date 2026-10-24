"""统一后端 API 层（ui）。

三种启动模式（CLI/Web/Desktop）复用同一内核与同一 LLM 配置源，走同一套
API：会话 / 循环（SSE 流式）、记忆、工具、LLM 配置；CLI 的 Textual 层也不绕过。

对应接口：doc/03-interfaces/ui-interface.md §1
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

from core.beast import BeastActivator, BeastError
from core.configuration import ConfigManager, ConfigurationError
from core.configuration.models import LLMConfig
from core.diagnostics import Deps
from core.loop import DefaultLoop, LimitsConfigurable, LoopEvent, LoopPlugin
from core.memory import MemoryStore, TranscriptStore
from core.orchestration import OrchestrationError, TaskScheduler
from core.permission import ApprovalChannel
from core.pet.core import PetActivator, PetControl
from core.tools import ToolDef, ToolProvider, ToolResult
from core.tools.env_shell import EnvironmentSnapshot

from .errors import UiError, UiErrorCode
from .models import Event
from .plan import PlanDraft, PlanSessions
from .sessions import SessionRegistry

# LoopEvent 类型 → SSE 事件类型（DefaultLoop 产出七类 LoopEvent，spec：异步流式执行）。
# 增量与终态**分属两型**（change `0132` / ADR-0125 / 账本 E65）：`reply_delta` ⇒ `loop.delta`
# （载荷恒为 `{"text": …}`），`loop_finished` ⇒ `loop.result`（载荷 `LoopResult`）。共型曾令
# Web 前端按「无 reply 即序列化 JSON」处理增量帧 ⇒ 逐帧渲染 JSON。
_EVENT_MAP = {
    "loop_started": "session.created",
    "step_completed": "loop.action",  # 既有契约（回合推进），不随动作事件新增而改名
    "action_started": "loop.action_started",
    "action_completed": "loop.action_completed",
    "reply_delta": "loop.delta",
    # 思考回显（change `0145` / ADR-0137）：**有意**同名透传 —— 与 `loop.delta` 载荷同形
    # （`{"text": …}`）而类型相异，三端据此分落折叠块与正文。显式登记而非依赖 `_map_event`
    # 的 identity 兜底，使本表始终是「LoopEvent → SSE 类型」的完整契约面。
    "loop.reasoning": "loop.reasoning",
    # 轮内压实进度（change 0256）：前后各一条，三端据此显示「压缩中 / 已压缩」。
    "loop.compacting": "loop.compacting",
    "loop.compacted": "loop.compacted",
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
    cfg: LLMConfig,
    *,
    output_reserve: int | None,
    max_rounds: int | None,
    history_turns: int | None = None,
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
    if history_turns is not None:
        loop["history_turns"] = history_turns
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
        # 只读计划循环（change 0313）：工具面仅 READ 级且排除 tools.delegate。
        plan_loop: LoopPlugin | None = None,
        pet_activator: PetActivator | None = None,
        pet_control: PetControl | None = None,
        beast_activator: BeastActivator | None = None,
        registry: SessionRegistry | None = None,
        transcript: TranscriptStore | None = None,
        diagnostics: Deps | None = None,
        env_snapshot: EnvironmentSnapshot | None = None,
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
        self._plan_loop = plan_loop
        self._plan_sessions = PlanSessions()
        self._pet_activator = pet_activator
        self._pet_control = pet_control
        # 神兽三入口（斜杠 / WebUI 自然语言）缺省未接 ⇒ 报 `UI_BEAST_UNSET`（对称 pet）
        self._beast_activator = beast_activator
        self._registry = registry if registry is not None else SessionRegistry()
        # 对话转录存储（缺省未注入 ⇒ 枚举不做富化、`session_messages` 走空，形状不变）
        self._transcript = transcript
        # 只读诊断源（change 0163 / ADR-0154）：**单一接缝** —— 句柄由组合根装配后整体注入，
        # 本层不拆句柄（缺省未接线 ⇒ TUI 只读命令给提示而非崩）
        self._diagnostics = diagnostics
        # 运行环境事实（change 0240）：活动标题在未显式给 type 时按有效平台缺省命名。
        self._env_snapshot = env_snapshot
        self._llm_config: LLMConfig | None = None

    @property
    def approval(self) -> ApprovalChannel | None:
        """交互审批通道（高风险工具 confirm 门的终端 y/n）；非交互入口为 None。"""
        return self._approval

    @property
    def default_shell(self) -> str | None:
        """平台默认 shell 方言（未注入环境快照 ⇒ None，呈现层用中性 `Shell`）。"""
        return None if self._env_snapshot is None else self._env_snapshot.default_shell

    def diagnostics(self) -> Deps | None:
        """只读诊断源（`/doctor` `/status` 等只读命令的取数面）；未接线为 None。

        与 CLI 侧**同一**源（`core.diagnostics`）—— TUI 不另写检查逻辑；本层只做**取数接缝**。
        """
        return self._diagnostics

    # ---- 会话与循环 ----

    def create_session(self, mode: str) -> str:
        """新建会话，返回 session_id（经注册表登记，落盘注册表则跨进程可见）。"""
        return self._registry.create(mode)

    def list_sessions(self) -> list[dict[str, object]]:
        """枚举已登记对话会话（`{session_id, mode, created_at}`）。

        注入转录存储时**附派生** `title`（该会话首条用户消息截断，无则空串）与
        `updated_at`（最近一条转录时间戳，无转录则回落注册表 `created_at`）；派生值
        **不写注册表**（避免第二真源）。未注入 ⇒ 形状不变（既有消费方不受影响）。
        """
        entries = self._registry.list()
        if self._transcript is None:
            return entries
        summaries = self._transcript.summaries()
        enriched: list[dict[str, object]] = []
        for entry in entries:
            summary = summaries.get(str(entry.get("session_id", "")), {})
            enriched.append(
                {
                    **entry,
                    "title": summary.get("title", ""),
                    "updated_at": summary.get("updated_at", entry.get("created_at", 0.0)),
                }
            )
        return enriched

    def session_messages(self, session_id: str) -> list[dict[str, object]]:
        """该会话的对话转录（按追加次序）；未登记标识仍拒绝（不放宽会话校验）。"""
        self._require_session(session_id)
        if self._transcript is None:
            return []
        return self._transcript.read(session_id)

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
        async for loop_event in self._loop.astream(user_input, session_id=session_id):
            yield self._map_event(session_id, loop_event)

    async def run_task(self, session_id: str, goal: str) -> AsyncIterator[Event]:
        """SSE 流式输出编排任务进度事件（task.* 前缀）；进度事件与 CLI task 入口同构。"""
        self._require_session(session_id)
        if self._orchestrator is None:
            raise UiError(UiErrorCode.UI_ORCHESTRATOR_UNSET, "编排器未注入（任务入口不可用）")
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        async for task_event in self._orchestrator.astream(task_id, goal, session_id=session_id):
            yield Event(type=f"task.{task_event.type}", payload=task_event.payload)

    # ---- 会话级执行模式与计划审批（change 0313 / ADR-0303） ----

    def agent_mode(self, session_id: str) -> str:
        """读会话执行模式（缺省 ``quick``）；未登记会话 ⇒ `UI_SESSION_NOT_FOUND`。"""
        self._require_session(session_id)
        return self._plan_sessions.mode(session_id)

    def set_agent_mode(self, session_id: str, mode: str) -> None:
        """置会话执行模式；非法值 ⇒ `UI_PLAN_MODE_INVALID`（不静默归一）。"""
        self._require_session(session_id)
        self._plan_sessions.set_mode(session_id, mode)

    async def run_plan_turn(self, session_id: str, user_input: str) -> AsyncIterator[Event]:
        """计划轮：只读勘察 → 拆解草案 → `plan.draft_ready`（不含勘察原文）。"""
        self._require_session(session_id)
        if self._plan_sessions.mode(session_id) != "plan":
            raise UiError(UiErrorCode.UI_PLAN_MODE_INVALID, "当前会话不在计划模式")
        if self._plan_loop is None or self._orchestrator is None:
            raise UiError(UiErrorCode.UI_PLAN_UNAVAILABLE, "计划能力未注入（只读循环 / 编排器）")
        exploration = ""
        async for loop_event in self._plan_loop.astream(user_input, session_id=session_id):
            payload = loop_event.payload
            if loop_event.type == "reply_delta" and isinstance(payload, dict):
                data = cast(dict[str, Any], payload)
                text = data.get("text", "")
                if isinstance(text, str):
                    exploration += text
            elif loop_event.type == "loop_finished":
                reply = getattr(loop_event.payload, "reply", "") or ""
                if reply:
                    exploration = reply
            yield self._map_event(session_id, loop_event)
        # 拆解为阻塞式 LLM 调用（可达数十秒）：先给阶段信号，呈现端不停在勘察态
        yield Event(type="plan.drafting")
        try:
            plan = await self._orchestrator.draft_plan(user_input, context=exploration)
        except OrchestrationError as exc:
            raise UiError(UiErrorCode.UI_PLAN_DRAFT_FAILED, f"计划拆解失败：{exc}") from exc
        draft = PlanDraft(
            draft_id=f"draft-{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            goal=user_input,
            plan=plan,
            exploration=exploration,
            created_at=time.time(),
        )
        self._plan_sessions.put(draft)
        yield Event(type="plan.draft_ready", payload=self._draft_payload(draft))

    async def approve_plan(self, session_id: str, draft_id: str) -> AsyncIterator[Event]:
        """按已批准计划执行（`self_run=True`）；开始执行**前**即回 ``quick``。"""
        self._require_session(session_id)
        if self._orchestrator is None:
            raise UiError(UiErrorCode.UI_PLAN_UNAVAILABLE, "编排器未注入（计划执行不可用）")
        draft = self._plan_sessions.take(session_id, draft_id)
        if draft is None:
            raise UiError(
                UiErrorCode.UI_PLAN_DRAFT_NOT_FOUND, f"计划草案 {draft_id} 不存在或已消费"
            )
        self._plan_sessions.set_mode(session_id, "quick")
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        async for task_event in self._orchestrator.astream(
            task_id,
            draft.goal,
            plan=draft.plan,
            session_id=session_id,
            self_run=True,
        ):
            yield Event(type=f"task.{task_event.type}", payload=task_event.payload)

    def discard_plan(self, session_id: str, draft_id: str) -> bool:
        """丢弃草案并回 ``quick``；返回是否确有草案被丢弃。"""
        self._require_session(session_id)
        discarded = self._plan_sessions.discard(session_id, draft_id)
        self._plan_sessions.set_mode(session_id, "quick")
        return discarded

    @staticmethod
    def _draft_payload(draft: PlanDraft) -> dict[str, object]:
        """草案事件载荷：目标 / 子任务 / 依赖 / 波次 / 成功标准（**不含**勘察原文）。"""
        plan = draft.plan
        return {
            "draft_id": draft.draft_id,
            "goal": draft.goal,
            "subtasks": [
                {
                    "id": s.id,
                    "goal": s.goal,
                    "acceptance": s.acceptance,
                    "depends_on": list(s.depends_on),
                }
                for s in plan.subtasks
            ],
            "waves": [list(w) for w in plan.waves],
            "success_criteria": list(plan.success_criteria),
        }

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

    async def flush_post_turn(self, session_id: str) -> bool:
        """等待本会话轮末后台收尾链收束（change 0315 / ADR-0305）。

        供 TUI `/exit` 使用：返回是否在既有上限内收束（无在途 ⇒ ``True``）。
        自定义 loop 未提供该接缝 ⇒ 视为无在途收尾（不报错）。
        """
        self._require_session(session_id)
        flush = cast(
            "Callable[[], Awaitable[bool]] | None",
            getattr(self._loop, "flush_post_turn", None),
        )
        if not callable(flush):
            return True
        return bool(await flush())

    def compact(self, session_id: str) -> None:
        """压缩**本会话**记忆：触发存储层真实压实（按会话聚合摘要 + 重要度写回，可撤销）。

        ``session_id`` 经**关键字**传入存储层的**收窄形参**（change `0131` / ADR-0124 / 账本 E66）：
        此前按位置传入而被当成 ``query`` ⇒ 压实跑遍**全库**所有会话（「压缩本会话」会顺手提炼并
        归档他会话条目）。
        """
        self._require_session(session_id)
        if self._memory is not None:
            self._memory.compact(session_id=session_id)

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

    # ---- 神兽（WebUI 自然语言 + 前台 `/summon` `/recall`，change 0137 / 账本 E74） ----

    async def activate_beast(self, user_input: str) -> str:
        """WebUI 自然语言「召唤 X 兽做 Y」入口（对称 `activate_pet`）；返回神兽 agent_id。

        神兽激活 = 异步 handoff（beast-mode spec「Async Concurrent Execution」）⇒ 本方法为 async。
        """
        if self._beast_activator is None:
            raise UiError(UiErrorCode.UI_BEAST_UNSET, "神兽激活器未接")
        try:
            session = await self._beast_activator.activate_from_nl(user_input)
        except (OrchestrationError, BeastError) as exc:
            raise self._beast_error(exc) from exc
        return session.beast.agent_id

    async def beast_command(self, verb: str, target: str, *, task: str = "") -> dict[str, object]:
        """前台 `/summon <兽> [任务]` · `/recall <兽>` 控制面（与 CLI 同一激活器）。

        返回 `result_summary()` 摘要 + 会话 `state` —— 结果正文**只经只读查询面**取用
        （beast-mode spec「Task Result Visibility」：不检索、不落 L2、不编造）。
        """
        if self._beast_activator is None:
            raise UiError(UiErrorCode.UI_BEAST_UNSET, "神兽激活器未接")
        try:
            if verb == "summon":
                session = await self._beast_activator.activate_from_slash(target, task)
            elif verb == "recall":
                session = self._beast_activator.recall_from_slash(target)
            else:
                raise UiError(UiErrorCode.UI_BEAST_UNKNOWN_VERB, f"未知神兽控制动词：{verb}")
        except (OrchestrationError, BeastError) as exc:
            raise self._beast_error(exc) from exc
        return {**session.result_summary(), "state": session.state.value}

    @staticmethod
    def _beast_error(exc: OrchestrationError | BeastError) -> UiError:
        """领域错误在 UI 边界归一（不向 UI 抛裸领域异常）。

        无匹配神兽（`NO_AGENT_MATCH`）⇒ `UI_BEAST_NOT_FOUND`；状态冲突
        （`BEAST_ALREADY_MANIFEST` 重复召唤 / `BEAST_NOT_MANIFEST` 无在岗可召回）⇒
        `UI_BEAST_STATE_INVALID` —— 两者用户可见语义不同，不并作一码。
        """
        if isinstance(exc, OrchestrationError):
            return UiError(UiErrorCode.UI_BEAST_NOT_FOUND, str(exc))
        return UiError(UiErrorCode.UI_BEAST_STATE_INVALID, str(exc))

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
        history_turns: int | None = None,
    ) -> None:
        """用户保存 LLM 配置：校验 → 原子落盘 → 生效 → 热推预算上限（change `0099`）。

        有配置源时按 ``entry._config_set`` 范式（apply_change → write_patch → 重读）；无配置源
        （裸 ``UIAPILayer``）降级为纯内存 + 尽力热生效，不假装持久化。非法取值、落盘失败一律
        归为 ``UI_LLM_CONFIG_INVALID``，且**内存与 yaml 均回退到原值**。
        """
        _require_ref(cfg.api_key_ref)
        patch = _llm_patch(
            cfg, output_reserve=output_reserve, max_rounds=max_rounds, history_turns=history_turns
        )
        limits: tuple[int | None, int | None]
        turns: int | None = None
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
            turns = self._config.history_turns()
        else:
            limits = (max_rounds, _derive_budget(cfg, output_reserve))

        self._llm_config = cfg
        if isinstance(self._loop, LimitsConfigurable):
            self._loop.set_limits(max_rounds=limits[0], token_budget=limits[1], history_turns=turns)

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
