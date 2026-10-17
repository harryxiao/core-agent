"""默认智能体循环实现（DefaultLoop）。

把「观察→推理→行动→记忆」串成单轮闭环：异步为主（arun/astream）、同步为
薄壳（run）；不可逆动作过确认门，失败按 trace 回滚；横切中间件按序执行、
被拒短路；循环次数 / token 预算超限即终止，达阈值时压实上下文与记忆
（含固化打分与遗忘归档）。

对应接口：doc/03-interfaces/loop-interface.md §1
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import time
import uuid
import warnings
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Sequence, Sized
from typing import Any, cast

from core.context import Compactor, ContextError, WindowPlan, estimate_tokens, plan_window
from core.judgment import DecisionResult, DecisionRouter
from core.memory import MemoryEntry, MemoryStore, TranscriptStore, redact_secrets
from core.observability import TraceEvent, TraceLogger, Tracer
from core.plugin_registry import Plugin
from core.tools import SafetyGate, ToolProvider

from .protocol import (
    ActFn,
    Action,
    ActionResult,
    LoopContext,
    LoopEvent,
    LoopResult,
    Thinking,
    collect_result,
    current_session_id,
)

# 中间件契约：返回 Action 放行/改写，返回 None 表示拒绝（短路）。
Middleware = Callable[[LoopContext, Action], Action | None]

# 审批回调：不可逆动作经确认门判 confirm 时询问人工（tool_id, args, reason）→ 是否放行。
Approver = Callable[[str, dict[str, Any], str], Awaitable[bool]]

# 收尾观察者：每轮收尾时提交（任务文本, 行动/结果序列, 本轮成功与否）→ 观察产物（不返回值）。
# 成功与失败都提交（失败信号是技能迭代的判据）；loop 不 import skills（架构红线），
# 生产侧注入组合根闭包（内部再分发到 SopExtractor / 技能反馈）。
TurnObserver = Callable[[str, list[str], bool], object]

# 冷路径回调：收尾维护节拍给出一次进化冷路径机会（无参、不返回）；缺省未注入则不做。
# loop 不 import evolution（架构红线），生产侧注入组合根闭包（内部调 EvolutionWorker.maybe_run）。
ColdPath = Callable[[], None]

# 任务前 Consult 钩子：任务文本 → 文档化笔记摘要文本（确定性、纯读）；缺省未注入则不做。
# loop 不 import notes（架构红线），生产侧注入组合根闭包（内部调 NoteStore.digest）。
NotesConsult = Callable[[str], str]

# 常驻（pinned）笔记钩子：**零参** → 任务级硬约束注入块文本（确定性、纯读）；缺省未注入则不做。
# **零参即契约**：常驻注入与当轮任务无关（不因 query 未命中而缺席）；loop 不 import notes（红线），
# 生产侧注入组合根闭包（内部调 NoteStore.pinned_digest）。
PinnedNotesConsult = Callable[[], str]

# 既往失败教训钩子：**会话标识** → 失败教训注入块文本（确定性、纯读）；缺省未注入则不做。
# **入参即契约**：教训按**会话**取用（与 `notes_consult` 的任务文本入参、`pinned_notes_consult`
# 的零参**各不相同** —— 取数维度决定 arity）；loop 不 import memory 的语义面（红线），
# 生产侧注入组合根闭包（内部调 MemoryStore.failure_lessons）。见 change 0217 / ADR-0207。
FailureLessonsConsult = Callable[[str], str]

# trace 完成回调：本轮遥测记录完毕后按**轮**提交 trace_id（登记一条已完成 trace）；缺省不做。
# 与冷路径回调**节律不同**（不随维护节拍节流）；loop 不 import evolution（架构红线），
# 生产侧注入组合根闭包（内部调 EvolutionWorker.on_trace_complete）。
TraceObserver = Callable[[str], None]

# 结果侧观察者：每个非终止动作完成后回调（上下文, 动作, 执行结果）→ 无返回值；仅通知，
# 单个观察者异常降级留痕、不改本轮结局。loop 不 import constraints（架构红线），
# 生产侧注入组合根适配层闭包。
ActionObserver = Callable[[LoopContext, Action, ActionResult], None]

# 会话轮级检查点回调：``(trace_id, session_id, goal, done)`` → 无返回值；缺省未注入则不做。
# 轮首 ``done=False``、轮末 ``done=True``，两次共用同一 ``trace_id`` ⇒ 同一 task id 承载该轮的
# 「在途 / 完结」两态。loop **不 import** durability（架构红线），生产侧注入组合根闭包；
# 写入失败的降级策略（只告警、不改变本轮结局）由注入侧负责（change 0214 / ADR-0204）。
TurnCheckpoint = Callable[[str, str, str, bool], None]


_MAINTENANCE_INTERVAL_S = 900.0  # 记忆维护节拍（秒）：默认 15 分钟
# 单次压实耗时上限（秒，change 0256）：正常压实实测约 38s；超限即放行本轮，
# 避免同步模型调用把事件循环上的其余任务无限期挂起。`None` ⇒ 不设限。
_COMPACT_TIMEOUT_SECONDS = 120.0
_MAX_ACTION_EXCERPT = 400  # 动作事件 args/output 节选上界（事件面有界）
_MAX_STEP_VALUE = 80  # 行动序列单参数值摘要上界（change 0171 / ADR-0162）
_MAX_STEP_LINE = 300  # 行动序列整行上界（change 0171 / ADR-0162）
_MAX_MEMORY_ENTRY = 2048  # 单条 L2 沉淀条目长度上界（轨迹/行动序列/失败三条共用）
_FAILURE_REASON_FALLBACK = "终止动作未达成"  # 轮级失败无 `limit_reason` 时的恒定兜底文案
_FAILURE_STEP_MARK = "错误："  # 失败动作的渲染前缀（`_summarize_result`），供失败条目筛行


def _args_excerpt(args: dict[str, Any]) -> dict[str, Any]:
    """动作参数节选：恒为映射、逐值有界（≤ ``_MAX_ACTION_EXCERPT``）。

    过长字符串就地截断并加省略号；非字符串超长值退化为有界 ``str``。
    保留 dict 结构 ⇒ TUI 标题可取白名单字段（如 ``script`` / ``task`` / ``path``），
    避免整包 ``str(args)`` 截断后变成空 ``Bash()``（change 0233 / ADR-0160 根治）。
    """
    out: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str):
            if len(value) <= _MAX_ACTION_EXCERPT:
                out[key] = value
            else:
                out[key] = value[:_MAX_ACTION_EXCERPT] + "…"
            continue
        if isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
            continue
        text = str(value)
        out[key] = text if len(text) <= _MAX_ACTION_EXCERPT else text[:_MAX_ACTION_EXCERPT] + "…"
    return out


def _trajectory_line(item: Any) -> str:
    """轨迹项渲染为记忆行：``reply`` 取语义正文，dict 取轮次/成败/错误，其余退化为 str。"""
    if not isinstance(item, dict):
        return str(item)
    data = cast(dict[str, Any], item)
    if "reply" in data:
        return str(data["reply"])
    parts = [f"round {data.get('round')}", "ok" if data.get("ok") else "failed"]
    error = data.get("error")
    if error:
        parts.append(str(error))
    return " ".join(parts)


def _task_text(ctx: LoopContext) -> str:
    """本轮任务文本（perceive 写入的首条 user 消息）。"""
    for message in ctx.messages:
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def _action_steps(ctx: LoopContext) -> list[str]:
    """行动/结果序列（人类可读）：每个工具动作一行「工具名（参数摘要）→ 结果节选」。

    供收尾观察者（SOP 提炼 / 笔记写回）消费 —— **不落** ReAct 消息原文（助手动作的
    ``{"tool_id":…}`` / 工具观察的 ``{"data":…}`` JSON 转储）与整篇工具输出（change 0171 /
    ADR-0162）。终止动作不产生行动消息（``_record_observation`` 对 ``is_terminal`` 早退），
    故纯文字回复轮返回空列表 —— 写回侧「有意义闸门」据此跳过。
    """
    messages = ctx.messages
    steps: list[str] = []
    index = 1
    while index < len(messages):
        action = _decode_action(messages[index])
        if action is None:
            index += 1
            continue
        line = f"{action[0]}（{_summarize_args(action[1])}）"
        if index + 1 < len(messages) and _role(messages[index + 1]) == "tool":
            line += f" → {_summarize_result(messages[index + 1])}"
            index += 1
        steps.append(line[:_MAX_STEP_LINE])
        index += 1
    return steps


def failure_digest(
    trajectory: list[Any], steps: Sequence[str], *, reason: str = "", task: str = ""
) -> str:
    """轮级失败的沉淀摘要（change 0179 / ADR-0170）：任务 + 原因 + 失败轮次 + 失败动作。

    只为**轮级**失败服务（终止动作失败 / 预算或轮次终止 / 不可解析输出）—— 轮内自愈的工具
    失败不入此列（判据在调用方）。逐行经 ``redact_secrets`` 脱敏（与行动序列条目**同源**、
    方向 over-redact），整体受 ``_MAX_MEMORY_ENTRY`` 约束。``reason`` 为空（如不可解析输出轮）
    时以恒定兜底文案补齐首行 ⇒ 产物**恒非空**。``raw_output`` **不得**经此入记忆（承 0170 /
    ADR-0161）。
    """
    lines: list[str] = []
    if task:
        lines.append(f"任务：{task}"[:_MAX_STEP_LINE])
    lines.append(f"失败：{reason or _FAILURE_REASON_FALLBACK}")
    lines.extend(
        _trajectory_line(item)
        for item in trajectory
        if isinstance(item, dict) and cast(dict[str, Any], item).get("ok") is False
    )
    lines.extend(step for step in steps if _FAILURE_STEP_MARK in step)
    return "\n".join(redact_secrets(line) for line in lines)[:_MAX_MEMORY_ENTRY]


def _role(message: Any) -> str:
    """消息角色（非 dict ⇒ 空串）。"""
    if not isinstance(message, dict):
        return ""
    return str(cast("dict[str, Any]", message).get("role", ""))


def _loads(text: Any) -> Any:
    """``json.loads`` 容错包装：非字符串 / 非法 JSON ⇒ ``None``（渲染失败绝不外溢）。"""
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _decode_action(message: Any) -> tuple[str, dict[str, Any]] | None:
    """助手动作消息 → ``(工具名, 参数字典)``；非 ``{"tool_id": str}`` 形态 ⇒ ``None``。"""
    if not isinstance(message, dict):
        return None
    data = cast("dict[str, Any]", message)
    if data.get("role") != "assistant":
        return None
    payload = _loads(data.get("content"))
    if not isinstance(payload, dict):
        return None
    fields = cast("dict[str, Any]", payload)
    tool_id = fields.get("tool_id")
    if not isinstance(tool_id, str) or not tool_id:
        return None
    args = fields.get("args")
    return tool_id, cast("dict[str, Any]", args) if isinstance(args, dict) else {}


def _summarize_args(args: dict[str, Any]) -> str:
    """参数字典 → 人类可读摘要（``key: value`` 升序逗号连接；容器只报类型与规模）。"""
    return ", ".join(f"{key}: {_summarize_value(value)}" for key, value in sorted(args.items()))


def _summarize_value(value: Any) -> str:
    """单参数值 → 有界可读摘要；容器型只报 ``<type len=N>``（绝不 dump 正文）。"""
    if isinstance(value, str):
        return value[:_MAX_STEP_VALUE] + "…" if len(value) > _MAX_STEP_VALUE else value
    if value is None or isinstance(value, (bool, int, float)):
        return str(value)
    return _summarize_container(value)


def _summarize_container(value: Any) -> str:
    """非标量参数值 → ``<type len=N>``（可计数）或 ``<type>``。"""
    name = type(value).__name__
    if isinstance(value, Sized):
        return f"<{name} len={len(value)}>"
    return f"<{name}>"


def _summarize_result(message: Any) -> str:
    """工具观察消息 → 有界节选；``{"error": …}`` 加「错误：」前缀，否则取 ``data`` 节选。"""
    if not isinstance(message, dict):
        return _output_excerpt(message)
    content = cast("dict[str, Any]", message).get("content")
    payload = _loads(content)
    if isinstance(payload, dict):
        observation = cast("dict[str, Any]", payload)
        if observation.get("error"):
            return f"错误：{_output_excerpt(observation['error'])}"
        if "data" in observation:
            return _output_excerpt(observation["data"])
    return _output_excerpt(content)


def _output_excerpt(value: Any) -> str:
    """动作输出节选：str 化截断（失败时 error，成功时 data）。"""
    return str(value or "")[:_MAX_ACTION_EXCERPT]


def _context_tokens(ctx: LoopContext) -> int:
    """记账口径：**装配进本轮提示词的全量内容**（回灌历史 + 本轮消息 + 分层摘要）。

    口径同共享估计器 ``context.estimate_tokens``（跨条累计、每条至少 1）。planner 另行装配的
    系统提示与工具 schema 不在 ``ctx`` 内，由 :meth:`DefaultLoop._reported_prompt_tokens` 以
    **下界**补足（见 change 0152 / 账本 E96）。

    分层摘要住 system prompt（planner 装配），此处补足记账（change 0178 / ADR-0169）。
    **必须守卫空值**：``estimate_tokens("") == 1`` ⇒ 不守卫会给空字段记 1 token。
    """
    total = sum(
        estimate_tokens(str(cast("dict[str, Any]", message).get("content", "")))
        for message in (*ctx.history, *ctx.messages)
        if isinstance(message, dict)
    )
    for text in (ctx.summary_long, ctx.summary_mid):
        if text.strip():
            total += estimate_tokens(text)
    return total


class DefaultLoop(Plugin):
    """默认执行循环：ReAct 式「观察→推理→行动→记忆」闭环。"""

    plugin_id = "loop.default"
    generation = 1
    schema: dict[str, object] = {"type": "object"}
    coeffects = ["model:adapter", "memory:store", "tools:provider", "constitution:v1"]

    def __init__(  # noqa: PLR0913 — 注入面均为可选依赖注入
        self,
        *,
        planner: Callable[[LoopContext], Action | Awaitable[Action]] | None = None,
        memory: MemoryStore | None = None,
        tools: ToolProvider | None = None,
        gate: SafetyGate | None = None,
        middlewares: list[Middleware] | None = None,
        action_observers: list[ActionObserver] | None = None,
        tracer: Tracer | None = None,
        router: DecisionRouter | None = None,
        approver: Approver | None = None,
        compactor: Compactor | None = None,
        turn_observer: TurnObserver | None = None,
        notes_consult: NotesConsult | None = None,
        pinned_notes_consult: PinnedNotesConsult | None = None,
        failure_lessons_consult: FailureLessonsConsult | None = None,
        cold_path: ColdPath | None = None,
        trace_observer: TraceObserver | None = None,
        source: str = "loop",
        max_rounds: int = 10,
        token_budget: int = 65536,
        transcript: TranscriptStore | None = None,
        history_turns: int = 20,
        maintenance_interval: float = _MAINTENANCE_INTERVAL_S,
        # 单次压实耗时上限（秒，change 0256）：超时 ⇒ 留痕 `maintenance_failed`
        # （step=`compaction_timeout`）并放行本轮；`None` ⇒ 不设限（既有行为）。
        compact_timeout: float | None = _COMPACT_TIMEOUT_SECONDS,
        clock: Callable[[], float] | None = None,
        # 情景链的**时序相邻标注**开关（change 0202 / ADR-0192，缺省**关**）。开启 ⇒ 轮级失败
        # 条目的 `tags` 增 `after:<同会话上一已记忆轮>`；关闭 ⇒ 失败条目**逐字不变**。
        # 前序取自**进程内**按会话表 `_last_trace`（零记忆读 ⇒ 零新副作用）。
        causal_links: bool = False,
        # 执行接缝包装器（change 0209 / ADR-0199，缺省 `None`）。注入 ⇒ 包裹 `self.act`
        # （容错重试）；`None` ⇒ `self._act is self.act`，既有路径**逐字不变**。
        act_wrapper: Callable[[ActFn], ActFn] | None = None,
        # 会话轮级检查点回调（change 0214 / ADR-0204，缺省 `None`）。注入 ⇒ 轮首 / 轮末各写
        # 一次（在途 / 完结）；`None` ⇒ **零调用、零 I/O**，既有路径**逐字不变**。
        turn_checkpoint: TurnCheckpoint | None = None,
    ) -> None:
        self._planner = planner
        self._memory = memory
        self._tools = tools
        self._gate = gate if gate is not None else SafetyGate()
        self._middlewares = list(middlewares or [])
        self._action_observers = list(action_observers or [])
        self._tracer = tracer
        # 工具调用遥测的生产者 API（唯一生产者；未注入 tracer ⇒ 不产，见 `_log_tool_call`）
        self._trace_logger = TraceLogger(tracer) if tracer is not None else None
        self._router = router
        self._approver = approver
        self._compactor = compactor
        self._turn_observer = turn_observer
        self._notes_consult = notes_consult
        self._pinned_notes_consult = pinned_notes_consult
        self._failure_lessons_consult = failure_lessons_consult
        self._cold_path = cold_path
        self._trace_observer = trace_observer
        # 落记忆的命名空间：主 Agent 缺省 "loop"；神兽 loop 由组合根注入 "beast.<agent_id>"
        self._source = source
        self._max_rounds = max_rounds
        self._token_budget = token_budget
        # 对话转录：按会话落盘本轮 (user 原话, 最终回复)；缺省未注入 ⇒ 零落盘零回灌
        self._transcript = transcript
        self._history_turns = history_turns
        self._maintenance_interval = maintenance_interval
        self._compact_timeout = compact_timeout
        self._clock = clock if clock is not None else time.monotonic
        self._last_maintenance = self._clock()
        self._causal_links = causal_links
        # 前一**已记忆**轮的 trace（按会话）；change 0202 / ADR-0192。**进程内实例状态** ⇒
        # 跨进程重启、以及三路 loop 实例之间**链路会断**（已登记为局限）。零 I/O、零效应，
        # 故**不受开关门控**（开关只门控标注的**写入**）⇒ 会话中途开启亦立即可用。
        self._last_trace: dict[str, str] = {}
        # 执行接缝：缺省即 `self.act` 本身（`act_wrapper` 为 None ⇒ **逐字不变**）；注入 ⇒ 包裹。
        self._act: ActFn = act_wrapper(self.act) if act_wrapper is not None else self.act
        # 会话轮级检查点外发口（缺省 None ⇒ 轮首/轮末均不调用，零 I/O、逐字不变；change 0214）
        self._turn_checkpoint = turn_checkpoint
        # 轮末后台收尾（turn_observer / maintain）：不得堵住 `loop_finished` 外发，否则 TUI
        # 「思考中」会挂到技能迭代与维护节拍跑完（生产事故：自然语言终态已上屏，spinner 仍计时）。
        self._post_turn_task: asyncio.Task[None] | None = None

    # ---- Plugin 生命周期 ----

    def set_limits(
        self,
        *,
        max_rounds: int | None = None,
        token_budget: int | None = None,
        history_turns: int | None = None,
    ) -> None:
        """运行期改预算上限（``None`` = 保持该项；change `0099`）。

        各值在每轮读取处生效 ⇒ 赋值即**下一轮**生效，无需重建循环。
        合法性由配置层把关（此处不重复校验）。
        """
        if max_rounds is not None:
            self._max_rounds = max_rounds
        if token_budget is not None:
            self._token_budget = token_budget
        if history_turns is not None:
            self._history_turns = history_turns

    def load(self) -> None:
        return None

    def unload(self) -> None:
        return None

    def check(self) -> bool:
        return True

    # ---- 三入口（异步为主、同步薄壳）----

    def run(self, user_input: str, *, session_id: str = "") -> LoopResult:
        return asyncio.run(self.arun(user_input, session_id=session_id))

    async def arun(self, user_input: str, *, session_id: str = "") -> LoopResult:
        """异步执行入口：只取终态（三态归一由 `collect_result` 单一实现）。

        ``collect_result`` 在 ``loop_finished`` 处提前返回 ⇒ 生成器其后不再推进；轮末
        收尾以后台 task 挂出，此处**等候收束**，保证 ``run``/``arun`` 语义仍含完整收尾。
        """
        result = await collect_result(self.astream(user_input, session_id=session_id))
        await self._await_post_turn()
        return result

    async def _reason_events(self, ctx: LoopContext) -> AsyncIterator[LoopEvent | Action]:
        """推理步事件流：planner 支持流式时逐 delta 转 reply_delta，末态产出 Action。

        planner 无 ``astream``（含 None/纯 callable）时退化为 reason()，仅产出单个
        Action，事件序与非流式实现完全一致。``Thinking`` item 转 ``loop.reasoning``
        （开启思考回显时 planner 才产出该 item ⇒ 事件面的开关在 planner 一侧把关）。
        """
        planner = getattr(self._planner, "astream", None)
        if planner is None:
            yield await self.reason(ctx)
            return
        async for item in planner(ctx):
            if isinstance(item, str):
                yield LoopEvent("reply_delta", {"text": item})
            elif isinstance(item, Thinking):
                # round 与同轮 action_started 对齐，供 TUI 按步归并 Thinking（change 0233）
                yield LoopEvent("loop.reasoning", {"text": item.delta, "round": ctx.rounds})
            else:
                yield item

    async def astream(self, user_input: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        """流式执行入口（薄包装）：中断轮留痕并封口（change 0256）。

        正常收尾由执行体自己调 `end_trace`（保持「trace 回调之后才封口」的既有顺序）；
        消费方提前关闭 / 取消 / 未收尾异常时，本包装补记 `loop_aborted` 并封口，
        使在途事件经导出器落盘，不再静默丢失。`collect_result` 在 `loop_finished`
        提前返回时，执行体已完成封口（`state["finished"]`），不会误留中断痕。
        """
        trace_id = self._start_trace(user_input)
        state: dict[str, bool] = {"finished": False}
        reason = "interrupted"
        try:
            async with contextlib.aclosing(
                self._astream_events(user_input, trace_id, state=state, session_id=session_id)
            ) as events:
                async for event in events:
                    yield event
        except BaseException as exc:  # noqa: BLE001 — 留痕后原样重抛（含取消 / GeneratorExit）
            reason = type(exc).__name__
            raise
        finally:
            if not state["finished"]:
                self._trace(trace_id, "loop_aborted", {"reason": reason})
                self._end_trace(trace_id)

    async def _astream_events(  # noqa: C901, PLR0912, PLR0915 — 主管线多分支长管道（事件面七类 + 工具调用遥测）
        self,
        user_input: str,
        trace_id: str,
        *,
        state: dict[str, bool],
        session_id: str = "",
    ) -> AsyncGenerator[LoopEvent, None]:
        yield LoopEvent("loop_started", {"trace_id": trace_id})
        self._trace(trace_id, "loop_started", {"trace_id": trace_id})
        # 与上一轮后台收尾串行：避免新一轮感知/记忆与旧轮技能迭代、维护节拍并发踩踏。
        await self._await_post_turn()
        ctx = self.perceive(user_input, session_id=session_id)
        self._consult_notes(ctx, trace_id)
        self._load_pinned_notes(ctx, trace_id)
        self._load_failure_lessons(ctx, trace_id)
        # 轮首写点（change 0214 / ADR-0204）：用户消息**已进**转录（`perceive` 内追加）、
        # 前置读（Consult / 常驻注入）**已完成** ⇒ 此处标记「本轮在途」。中断路径只补记
        # 遥测（change 0256），不写检查点 ⇒ 中途异常 / 被杀天然留未完结态（与编排波次回调同语义）。
        self._mark_turn(trace_id, session_id, ctx, done=False)
        limit_reason = ""
        # 推理产出不可用（解析失败 / 模型调用失败）的失败态终止动作 ⇒ 本轮失败（0166 / ADR-0156）。
        # 与 `limit_reason` **并列**：后者管**终止语义**（`loop_failed` 事件、合成文案、转录门控），
        # 本标记只管**成败记账**（收尾钩子 + `LoopResult.failed`），不改终止语义。
        turn_failed = False
        # 不可解析的原始产出（有界；change 0170 / ADR-0161）：只经 `LoopResult` 与 trace 外发，
        # **不进**转录（追加的是 `ctx.reply` 可读提示）与记忆（`remember` 收的也是 `reply`）。
        raw_output = ""
        # 本轮循环是否已流式外发**回复**增量（避免终态重复全文）。判据**只认** `reply_delta`：
        # 思考回显事件（`loop.reasoning`）与回复增量同形相异类，计入会吞掉终态补发。
        streamed = False
        # 本轮是否已压实（change 0182 / ADR-0173）：步数阈值小于轮数上限时，「步数 ≥ 阈值」
        # 在阈值步之后**步步为真**，若无此闸门则一轮内重复压实（每次含模型调用）。
        # 标记为本轮**执行态**（非上下文事实）⇒ 置于 `astream` 局部变量，随轮自然重置。
        compacted = False
        # 预算降级标记（change 0230 / G2）：每轮至多一次「强制压实 + 收尾轮」。
        # 压实不改变本轮消息记账（`ctx.token_used` 不因持久化而下降），故降级语义是
        # **给模型一轮收尾机会**：收尾轮完成即正常收口，仍未完成才按预算终止。
        budget_retried = False
        while not ctx.done():
            if ctx.rounds >= self._max_rounds:
                limit_reason = "LOOP_LIMIT_EXCEEDED"
                break
            action: Action | None = None
            async for item in self._reason_events(ctx):
                if isinstance(item, LoopEvent):
                    streamed = streamed or item.type == "reply_delta"
                    yield item
                else:
                    action = item
            assert action is not None  # noqa: S101 — _reason_events 末态必产 Action
            action = self._apply_middlewares(ctx, action)
            action, approved = await self._authorize(action)
            if not action.is_terminal:  # 终止动作（空 tool_id）非工具调用，不发
                yield LoopEvent(
                    "action_started",
                    {
                        "round": ctx.rounds,
                        "tool_id": action.tool_id,
                        "args": _args_excerpt(action.args),
                    },
                )
            act_t0 = time.monotonic()
            # 动作期会话归属（change 0247）：工具处理器（如 delegate）据此把发起会话
            # 转交子 Agent；`finally` 复位，异常不得把会话 ID 泄漏到后续调用。
            session_token = current_session_id.set(ctx.session_id)
            try:
                result = await self._act(action, trace_id, approved=approved)
            finally:
                current_session_id.reset(session_token)
            if action.is_terminal and result.failed:
                turn_failed = True  # 终止动作的失败态（工具动作失败不入此列：ReAct 多轮自愈）
                raw_output = action.raw_output  # 不可解析原始产出：另路留存，不进回复正文
            if not action.is_terminal:
                duration_ms = int((time.monotonic() - act_t0) * 1000)
                output = _output_excerpt(result.error if result.failed else result.data)
                # 遥测先于事件外发：不依赖消费方继续拉取生成器（同判据、同点、同载荷）
                self._log_tool_call(trace_id, action, result, latency_ms=duration_ms, output=output)
                yield LoopEvent(
                    "action_completed",
                    {
                        "round": ctx.rounds,
                        "tool_id": action.tool_id,
                        "ok": not result.failed,
                        "duration_ms": duration_ms,
                        "output": output,
                    },
                )
            self._notify_action_result(ctx, action, result, trace_id)
            self._record_observation(ctx, action, result)
            if result.failed:
                self.rollback(trace_id)
            ctx = self.observe(ctx, result)
            yield LoopEvent("step_completed", {"round": ctx.rounds, "failed": result.failed})
            self._trace(trace_id, "step_completed", {"round": ctx.rounds, "failed": result.failed})
            if not compacted and self._should_compact(ctx):
                # 卸载到工作线程：压实含**同步**模型调用（摘要 / 关键事实抽取）——`completion()`
                # 是 `asyncio.run` 薄壳，在事件循环线程上必抛；且其耗时为模型网络往返，
                # 在循环线程上执行会阻塞其余任务（change 0167 / ADR-0157）。
                # 前后各一条进度事件（change 0256）：消费方据此显示「压缩中」而非无响应。
                yield LoopEvent("loop.compacting", {"round": ctx.rounds})
                elapsed_ms, timed_out = await self._compact_bounded(ctx, trace_id)
                compacted = True
                yield LoopEvent(
                    "loop.compacted",
                    {
                        "round": ctx.rounds,
                        "elapsed_ms": round(elapsed_ms, 3),
                        "timeout": timed_out,
                    },
                )
            if self._token_budget > 0 and ctx.token_used >= self._token_budget:
                # 预算降级续跑（change 0230 / G2），语义见 `_budget_retry`。
                retry, compacted = await self._budget_retry(
                    ctx, trace_id, budget_retried=budget_retried, compacted=compacted
                )
                budget_retried = budget_retried or retry
                if retry:
                    continue
                if not (budget_retried and ctx.done()):
                    limit_reason = "TOKEN_BUDGET_EXCEEDED"
                    break
        turn_ok = not limit_reason and not turn_failed
        if limit_reason:
            ctx.reply = f"{limit_reason}: 本轮终止"
            yield LoopEvent("loop_failed", {"reason": limit_reason, "trace_id": trace_id})
        # 转录在 `remember` **之前**追加（记忆失败不牵连会话历史）；门控 `limit_reason`：
        # 上面刚把 `ctx.reply` 覆盖为**合成**终止文案，落盘即谎报模型原话。
        if not limit_reason:
            self._append_transcript(session_id, "assistant", ctx.reply)
        self.remember(
            trace_id,
            [*ctx.trajectory, {"reply": ctx.reply}],
            session_id=session_id,
            steps=_action_steps(ctx),
            failed=bool(limit_reason) or turn_failed,
            reason=limit_reason,
            task=_task_text(ctx),
        )
        # 轮末写点（change 0214 / ADR-0204）：成功路与 `limit_reason` 终止路**都**到达此处
        # （`remember` 在两分支之外） ⇒ 终止轮同样被标记完结。
        self._mark_turn(trace_id, session_id, ctx, done=True)
        self._trace(
            trace_id,
            "loop_finished",
            {
                "reply": ctx.reply,
                "failed": bool(limit_reason) or turn_failed,
                # 有则加：仅不可解析轮次才带该字段（其余轮次载荷逐字不变）
                **({"raw_output": raw_output} if raw_output else {}),
            },
            module_id="loop.default" if limit_reason else None,
        )
        # 本轮遥测已齐：交给 trace 完成回调（登记一条已完成 trace；缺省不启用）
        self._notify_trace_complete(trace_id)
        # 顺序约束：回调之后才封口（回调须能完整回放本轮事件；封口交付导出器 + 释放内存）
        self._end_trace(trace_id)
        # 正常收尾已完成封口 ⇒ 包装器不再补记 loop_aborted（change 0256）
        state["finished"] = True
        # 收尾钩子 + 维护节拍**后台**执行：二者均可含同步模型调用（0167），若 await 在
        # `loop_finished` 之前，TUI 终态已上屏却仍显示「思考中」。`collect_result` 在
        # `loop_finished` 提前返回 ⇒ 不可把 await 写在 yield 之后（会被 aclose 吞掉）。
        self._schedule_post_turn(ctx, trace_id, session_id, ok=turn_ok)
        if not streamed:  # 未流式外发过 delta 才补一次全文（非流式 planner 兼容路径）
            yield LoopEvent("reply_delta", {"text": ctx.reply})
        yield LoopEvent(
            "loop_finished",
            LoopResult(
                reply=ctx.reply,
                trace_id=trace_id,
                failed=bool(limit_reason) or turn_failed,
                raw_output=raw_output,
            ),
        )

    def _consult_notes(self, ctx: LoopContext, trace_id: str) -> None:
        """任务前 Consult：把注入钩子产出的文档化笔记摘要写入 ``ctx.notes``（缺省不启用）。

        钩子抛错仅降级留痕、置空摘要，**不改变本轮结局**；摘要经 planner 注入推理上下文。
        """
        if self._notes_consult is None:
            return
        try:
            ctx.notes = self._notes_consult(_task_text(ctx))
        except Exception as err:  # noqa: BLE001 — Consult 失败降级，不影响本轮结果
            ctx.notes = ""
            self._trace(trace_id, "notes_consult_failed", {"error": str(err)})

    def _load_pinned_notes(self, ctx: LoopContext, trace_id: str) -> None:
        """任务前常驻注入：把零参钩子产出的**常驻笔记块**写入 ``ctx.pinned_notes``（缺省不启用）。

        **每轮无条件**（钩子无任务文本入参 ⇒ 与 query 命中无关）；抛错仅降级留痕、置空，
        **不改变本轮结局**（与 ``_consult_notes`` 同口径）。
        """
        if self._pinned_notes_consult is None:
            return
        try:
            ctx.pinned_notes = self._pinned_notes_consult()
        except Exception as err:  # noqa: BLE001 — 常驻注入失败降级，不影响本轮结果
            ctx.pinned_notes = ""
            self._trace(trace_id, "pinned_notes_consult_failed", {"error": str(err)})

    def _load_failure_lessons(self, ctx: LoopContext, trace_id: str) -> None:
        """任务前注入：把**本会话的既往失败教训**块写入 ``ctx.failure_lessons``（缺省不启用）。

        **入参为本轮会话标识**（教训按会话取用 —— 与 ``_load_pinned_notes`` 的零参不同）；
        抛错仅降级留痕、置空，**不改变本轮结局**（与 ``_consult_notes`` / ``_load_pinned_notes``
        同口径）。置空（而非保留陈旧值）与 ``_consult_notes`` 的降级口径一致。
        """
        if self._failure_lessons_consult is None:
            return
        try:
            ctx.failure_lessons = self._failure_lessons_consult(ctx.session_id)
        except Exception as err:  # noqa: BLE001 — 教训注入失败降级，不影响本轮结果
            ctx.failure_lessons = ""
            self._trace(trace_id, "failure_lessons_consult_failed", {"error": str(err)})

    def _mark_turn(self, trace_id: str, session_id: str, ctx: LoopContext, *, done: bool) -> None:
        """轮级检查点外发：把本轮「在途 / 完结」交给注入的闭包（缺省不启用；change 0214）。

        契约 ``(trace_id, session_id, goal, done)``；轮首 ``done=False``、轮末 ``done=True``。
        ``goal`` 取本轮任务文本（``perceive`` 写入的首条 user 消息）⇒ 两次写点**同值**。
        闭包异常**不**在此吞：降级策略（持久化失败只告警、不改变本轮结局）是**注入侧**的
        契约（组合根闭包），与本类其余钩子「在此降级留痕」的分工不同 —— 那些钩子的产物
        入**上下文**，本钩子只**外发**事实。
        """
        if self._turn_checkpoint is None:
            return
        self._turn_checkpoint(trace_id, session_id, _task_text(ctx), done)

    def _schedule_post_turn(
        self, ctx: LoopContext, trace_id: str, session_id: str, *, ok: bool
    ) -> None:
        """把 ``turn_observer`` + ``maintain`` 挂为后台 task（不阻塞 ``loop_finished`` 外发）。

        收尾钩子 / 维护节拍均可含同步模型调用（0167）⇒ 必须 ``to_thread``；又因
        ``collect_result`` 在 ``loop_finished`` 提前返回，不可把 await 写在 yield 之后。
        """

        async def _run() -> None:
            await asyncio.to_thread(self._notify_turn, ctx, trace_id, ok=ok)
            await asyncio.to_thread(self._maintain, trace_id, session_id)

        self._post_turn_task = asyncio.get_running_loop().create_task(_run(), name="loop-post-turn")

    async def _await_post_turn(self) -> None:
        """等候上一轮后台收尾收束（无在途 task ⇒ 立即返回）。

        task 已被宿主取消（承载它的 event loop 关闭清理 —— ``run()`` 同步入口 /
        测试驱动每次 ``asyncio.run`` 新建 loop，旧轮 task 在旧 loop 上被 cancel）⇒
        **放行**：后台收尾本是尽力而为语义，取消态不得杀死新一轮。当前协程自身被
        取消（打断等）仍照常传播 —— 以 ``task.cancelled()`` 区分两者。
        """
        task = self._post_turn_task
        if task is None:
            return
        try:
            await task
        except asyncio.CancelledError:
            if not task.cancelled():
                raise  # 被取消的是当前协程（本轮被打断/清理）⇒ 照常传播
        finally:
            if self._post_turn_task is task:
                self._post_turn_task = None

    def _notify_turn(self, ctx: LoopContext, trace_id: str, *, ok: bool) -> None:
        """收尾钩子：把任务文本 + 行动/结果序列 + 本轮成败交给注入的观察者（缺省不启用）。

        ``ok=False`` 也提交（失败是技能迭代的判据），是否消费由观察者自决；观察者抛错
        仅降级留痕，不改变本轮结果与终止语义。
        """
        if self._turn_observer is None:
            return
        try:
            self._turn_observer(_task_text(ctx), _action_steps(ctx), ok)
        except Exception as err:  # noqa: BLE001 — 观察失败降级，不影响本轮结果
            self._trace(trace_id, "turn_observer_failed", {"error": str(err)})

    def _notify_trace_complete(self, trace_id: str) -> None:
        """收尾回调：本轮遥测已齐后提交 trace_id（登记一条已完成 trace；缺省不启用）。

        与维护节拍**无关**（按轮、不节流）；回调抛错仅降级留痕，不改变本轮结果与终止语义。
        """
        if self._trace_observer is None:
            return
        try:
            self._trace_observer(trace_id)
        except Exception as err:  # noqa: BLE001 — 登记失败降级，不影响本轮结果
            self._trace(trace_id, "trace_observer_failed", {"error": str(err)})

    def _maintain(self, trace_id: str, session_id: str = "") -> None:
        """收尾维护节拍：距上次维护达间隔才触发一次，各自失败降级（change 0178 扩为四步）。

        节拍含：①会话级记忆压实（产会话整体摘要）②中期摘要物化（中带 → 中层摘要）
        ③记忆遗忘 ④冷路径机会。``session_id`` 为**本轮**会话（缺省空串 ⇒ 跳过会话级两步）。
        间隔 ``<=0`` 关闭节拍；时钟经构造注入（可测）。节拍状态驻留实例（多会话共享一个节拍
        ⇒ 只有「正巧活跃」的会话被刷新）。四件事**各自失败降级、不中断本轮**。

        成本可观测（change 0253 / ADR-0243）：一次实际节拍产出**一条** ``maintenance`` 事件，
        payload 含 ``elapsed_ms``（总耗时）与 ``steps``（各步骤耗时毫秒）；步骤失败另记
        ``maintenance_failed`` 并带 ``step`` 归因。耗时用单调时钟，payload **不含**正文/摘要/
        会话标识。未注入 tracer ⇒ 零事件（``_trace`` 空转），既有行为逐字不变。
        """
        if self._maintenance_interval <= 0:
            return
        now = self._clock()
        if now - self._last_maintenance < self._maintenance_interval:
            return
        self._last_maintenance = now
        step_ms: dict[str, float] = {}

        def run(name: str, step: Callable[[], Any]) -> None:
            """计时执行一步；失败留痕（带 step 归因）不中断其余步骤。"""
            started = time.perf_counter()
            try:
                step()
            except Exception as err:  # noqa: BLE001 — 各自失败降级，本轮继续
                self._trace(trace_id, "maintenance_failed", {"step": name, "error": str(err)})
            finally:
                step_ms[name] = (time.perf_counter() - started) * 1000.0

        memory = self._memory
        if memory is not None:
            if session_id:
                run("session_compact", lambda: memory.compact(session_id=session_id))
                run("mid_summary", lambda: self._materialize_mid(session_id))
            run("forget", memory.forget)
        cold_path = self._cold_path
        if cold_path is not None:
            run("cold_path", cold_path)
        self._trace(
            trace_id,
            "maintenance",
            {
                "elapsed_ms": round(sum(step_ms.values()), 3),
                "steps": {name: round(ms, 3) for name, ms in step_ms.items()},
            },
        )

    def _materialize_mid(self, session_id: str) -> None:
        """物化会话滑窗「中带」的中期摘要（change 0178 / ADR-0169）。

        读转录切中带 → 空则**不调用**（幂等闸门）→ 包 prompt-only **桩**（``transcript.<i>``，
        **绝不落库**）→ ``memory.summarize_slice``。未注入转录 / 未注入 memory / ``session_id``
        为空 / 无中带 ⇒ 直接返回（零写入零效应）。
        """
        if self._transcript is None or self._memory is None or not session_id:
            return
        plan = self._window_plan(tiered=True)
        if plan.mid_turns <= 0:
            return
        _, mid_rows = self._transcript.window(
            session_id,
            short_turns=plan.short_turns,
            mid_turns=plan.mid_turns,
            short_tokens=plan.short_tokens,
        )
        if not mid_rows:
            return
        stubs = [
            MemoryEntry(
                id=f"transcript.{index}",
                layer="L2",
                content=f"{row.get('role', '')}: {row.get('content', '')}",
                tags=[],
                source="transcript",
                trace_id=f"compaction.mid.{session_id}",
                session_id=session_id,
                kind="episodic",
            )
            for index, row in enumerate(mid_rows)
        ]
        self._memory.summarize_slice(session_id, stubs, max_chars=plan.mid_chars)

    def _should_compact(self, ctx: LoopContext) -> bool:
        """**本轮工具步数**或 token 预算达阈值即触发压实（未注入压实器则永不触发）。

        ``ctx.rounds`` 是本轮内已记账的工具动作步数（每用户轮自 ``0`` 起算），**非**对话轮数：
        步数阈值须小于 ``max_rounds`` 才可能在本轮内提前触发（change 0182 / ADR-0173）。
        预算关闭（``token_budget <= 0``）时只按步数维度判定，避免 ``token_used >= 0``
        恒真导致每轮压实。
        """
        if self._compactor is None:
            return False
        if self._token_budget <= 0:
            return self._compactor.should_compact(ctx.rounds, 0, 1)
        return self._compactor.should_compact(ctx.rounds, ctx.token_used, self._token_budget)

    def _compact(self, ctx: LoopContext, trace_id: str, *, trigger: str = "threshold") -> None:
        """压实：**本轮**消息 + 工具 I/O 提炼沉淀（persist）→ 记忆固化（打分 + 摘要）→ 遗忘归档。

        输入是 ``ctx.messages``（**仅本轮**，多轮历史由三层滑窗 change 0178 与记忆压实承载 ——
        本方法不折入历史）。三步共用一次触发、任一步**降级不中断本轮**（原记忆保持不变，失败经
        观测通道记 ``maintenance_failed`` 留痕）；终止语义不变：压实后仍按既有预算/轮数条件终止。

        记忆固化**按本轮会话标识收窄聚合范围**（与维护节拍 ``_maintain`` 同口径，change 0192）：
        仅聚合该会话的 L2 episodic 条目，SHALL NOT 顺手提炼他会话条目；标识为空串时按全量聚合。

        成本可观测（change 0253 / ADR-0243）：一次压实产出**一条** ``compaction`` 事件，payload
        含 ``trigger``（``threshold`` / ``budget_retry``）、``elapsed_ms`` 与分步 ``steps``
        （``persist`` / ``memory_compact`` / ``forget``）；失败步骤另记 ``maintenance_failed``
        并带 ``step``。耗时用单调时钟，payload **不含**正文/摘要/会话标识。
        """
        assert self._compactor is not None  # noqa: S101 — 调用点已判空
        step_ms: dict[str, float] = {}
        started = time.perf_counter()
        try:
            self._compactor.persist(
                self._compactor.compact(ctx.messages), session_id=ctx.session_id
            )
        except ContextError:
            pass  # 无可沉淀关键信息：非错误，不替换原文
        except Exception as err:  # noqa: BLE001 — 压实失败降级，本轮继续
            self._trace(trace_id, "maintenance_failed", {"step": "persist", "error": str(err)})
        finally:
            step_ms["persist"] = (time.perf_counter() - started) * 1000.0

        memory = self._memory
        if memory is not None:

            def run(name: str, step: Callable[[], Any]) -> None:
                """计时执行一步；失败留痕（带 step 归因）不中断后续步骤。"""
                step_started = time.perf_counter()
                try:
                    step()
                except Exception as err:  # noqa: BLE001 — 各自失败降级，本轮继续
                    self._trace(trace_id, "maintenance_failed", {"step": name, "error": str(err)})
                finally:
                    step_ms[name] = (time.perf_counter() - step_started) * 1000.0

            run("memory_compact", lambda: memory.compact(session_id=ctx.session_id))
            run("forget", memory.forget)
        self._trace(
            trace_id,
            "compaction",
            {
                "trigger": trigger,
                "elapsed_ms": round(sum(step_ms.values()), 3),
                "steps": {name: round(ms, 3) for name, ms in step_ms.items()},
            },
        )

    async def _compact_bounded(
        self, ctx: LoopContext, trace_id: str, *, trigger: str = "threshold"
    ) -> tuple[float, bool]:
        """工作线程压实加耗时上限（change 0256），返回 ``(elapsed_ms, timed_out)``。

        压实含**同步**模型调用，正常实测约 38s；端点挂起时会把事件循环上的其余任务
        一并拖住。超限只取消「等待」，工作线程无法强杀（已登记为局限），但本轮立即
        放行，并经 ``maintenance_failed``（step=``compaction_timeout``）留痕。
        """
        started = time.perf_counter()
        timeout = self._compact_timeout
        call = asyncio.to_thread(self._compact, ctx, trace_id, trigger=trigger)
        try:
            if timeout is None:
                await call
            else:
                await asyncio.wait_for(call, timeout=timeout)
        except TimeoutError:
            self._trace(
                trace_id,
                "maintenance_failed",
                {"step": "compaction_timeout", "timeout_s": timeout},
            )
            return (time.perf_counter() - started) * 1000.0, True
        return (time.perf_counter() - started) * 1000.0, False

    async def _budget_retry(
        self, ctx: LoopContext, trace_id: str, *, budget_retried: bool, compacted: bool
    ) -> tuple[bool, bool]:
        """预算触顶降级（change 0230 / G2）：返回 ``(是否续跑, 压实标记)``。

        先强制压实（本轮至多一次），再给模型**一轮收尾机会**：压实不会降低本轮消息记账
        （``ctx.token_used`` 不因持久化而下降），故降级不能表现为「压完继续跑」，只能表现为
        「收尾轮完成即正常收口，否则按 ``TOKEN_BUDGET_EXCEEDED`` 终止」。未注入压实器
        或已降级过 ⇒ 不续跑，既有行为不变。
        """
        if budget_retried or self._compactor is None:
            return False, compacted
        if not compacted:
            # 与阈值压实共用同一耗时上限（change 0256）：预算降级路径同样阻塞本轮。
            await self._compact_bounded(ctx, trace_id, trigger="budget_retry")
            compacted = True
        ctx.token_used = max(_context_tokens(ctx), self._reported_prompt_tokens())
        self._trace(
            trace_id,
            "budget_retry",
            {"token_used": ctx.token_used, "token_budget": self._token_budget},
        )
        return True, compacted

    # ---- 阶段方法 ----

    def perceive(self, user_input: str, *, session_id: str = "") -> LoopContext:
        # 检索归 ContextEngine.assemble（架构图 :117）；perceive 只观察，不检索记忆。
        # ``session_id`` 只装入上下文包（供推理期检索/技能路由归属），不驻留循环实例。
        tools = self._tools.active_tools() if self._tools is not None else []
        # 次序不可颠倒：先取历史（不含本轮），再落本轮 user 行 —— 否则本轮被回灌两遍。
        # 分层：**先**读摘要定 `tiered`（有摘要才分层），再按配额切短带（change 0178）。
        summary_long, summary_mid = self._load_summaries(session_id)
        plan = self._window_plan(tiered=bool(summary_long or summary_mid))
        history = self._load_history(session_id, plan=plan)
        ctx = LoopContext(
            messages=[{"role": "user", "content": user_input}],
            tools=tools,
            session_id=session_id,
            history=history,
            summary_long=summary_long,
            summary_mid=summary_mid,
            # 区块配比的上游（change 0201 / ADR-0191）：预算**透传**给 planner，由后者按
            # 五区块份额派生注入额度。未启用（缺省）时 planner 忽略此值 ⇒ 行为逐字不变。
            token_budget=self._token_budget,
        )
        ctx.token_used = _context_tokens(ctx)
        self._append_transcript(session_id, "user", user_input)
        return ctx

    async def reason(self, ctx: LoopContext) -> Action:
        if self._planner is None:
            return Action(args={"reply": self._echo(ctx)})
        result = self._planner(ctx)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _authorize(self, action: Action) -> tuple[Action, bool]:
        """不可逆动作过确认门 + 审批通道；返回（可能被拒绝替换的）动作与是否已批准。"""
        if not action.is_irreversible:
            return action, False
        if await self._allow(action):
            return action, True
        return self.decline(action), False

    async def act(self, action: Action, trace_id: str, *, approved: bool = False) -> ActionResult:
        if action.is_terminal:
            # 终止动作的失败态（推理产出不可用）透出：本轮据此记为失败（change 0166 / ADR-0156）。
            return ActionResult(failed=action.failed, data=action.args)
        if self._tools is None:
            return ActionResult(failed=True, error="NO_TOOL_PROVIDER")
        result = await self._tools.ainvoke(
            action.tool_id, action.args, trace_id=trace_id, approved=approved
        )
        if result.ok:
            return ActionResult(failed=False, data=result.data)
        code = result.error.code if result.error is not None else "TOOL_ERROR"
        return ActionResult(failed=True, error=code)

    @staticmethod
    def _record_observation(ctx: LoopContext, action: Action, result: ActionResult) -> None:
        """观察回灌：工具调用与执行结果写入上下文消息（ReAct 多轮推进的前提）。"""
        if action.is_terminal:
            return
        ctx.messages.append(
            {
                "role": "assistant",
                "content": json.dumps(
                    {"tool_id": action.tool_id, "args": action.args}, ensure_ascii=False
                ),
            }
        )
        observation = {"error": result.error} if result.failed else {"data": result.data}
        ctx.messages.append(
            {"role": "tool", "content": json.dumps(observation, ensure_ascii=False)}
        )

    def observe(self, ctx: LoopContext, result: ActionResult) -> LoopContext:
        ctx.rounds += 1
        ctx.trajectory.append({"round": ctx.rounds, "ok": not result.failed, "error": result.error})
        data = result.data
        if isinstance(data, dict) and "reply" in data:
            ctx.reply = str(cast(dict[str, Any], data)["reply"])
            ctx.finish()
        # 记账 = max(全量装配估算, planner 探针观测)：系统提示与工具 schema 经探针计入，
        # provider 实报（可用时）抬升下界；无探针则退化为纯估算（同 change 0152 前口径的修正版）。
        ctx.token_used = max(_context_tokens(ctx), self._reported_prompt_tokens())
        return ctx

    def _reported_prompt_tokens(self) -> int:
        """planner 的提示 token 观测（记账**下界**；不可用 ⇒ 0）。

        duck-typing 消费（与 :meth:`_reason_events` 探 ``astream`` 同型）：planner 未暴露
        ``last_prompt_tokens`` / 探针抛错 / 返回非正值 ⇒ 0，退化为纯估算，不阻断本轮。
        """
        probe = getattr(self._planner, "last_prompt_tokens", None)
        if probe is None:
            return 0
        try:
            value = probe()
        except Exception:  # noqa: BLE001 — 探针异常降级为「无观测」，本轮继续
            return 0
        return value if isinstance(value, int) and value > 0 else 0

    def remember(  # noqa: PLR0913 — 注入面均为可选 keyword-only（缺省 ⇒ 逐字一致）
        self,
        trace_id: str,
        trajectory: list[Any],
        *,
        session_id: str = "",
        steps: Sequence[str] = (),
        failed: bool = False,
        reason: str = "",
        task: str = "",
    ) -> None:
        """把本轮轨迹沉淀为 L2 记忆（无行动不记忆）。

        轨迹项渲染为可读行（轮次/成败/错误），末条 ``reply`` 提供可检索的语义内容；
        ``session_id`` 记入条目，供压实/固化/遗忘按会话归组（缺省空串 = 未归属）；
        ``source`` 取构造注入的命名空间（缺省 ``"loop"``，神兽 loop 为 ``beast.<agent_id>``）。

        ``steps``（change 0173 / ADR-0164）非空时**另立一条** L2 条目承载本轮**行动与结果**序列
        —— 与轨迹条目**并存**、轨迹条目内容**除密钥形态脱敏外逐字不变**（写入前对整条内容
        ``redact_secrets``，change 0241）。另立而非合并：抽取器对**每条** L2 条目
        只取前 ``extract._MAX_ENTRY_CHARS``(400) 字符入 prompt，而 keyfact 的实体历来产自轨迹条目的
        **散文** ⇒ 合并会把散文顶出窗口。序列逐行经 ``redact_secrets`` 脱敏（判据与关键事实抽取
        **同源**，方向 over-redact）⇒ 密钥只引用不读取、绝不进记忆。缺省空 ⇒ 行为与变更前逐字一致。

        ``failed``（change 0179 / ADR-0170）为真时**再另立一条** ``loop.failure.<trace_id>``
        （``tags=["loop","failure"]``）承载轮级失败（任务 + ``reason`` + 失败轮次与失败动作）；
        该标签使压实材料**排除**它（见 ``memory.store._PRESERVE_TAGS``）⇒ 失败证据不被摘成中性
        总结、不被迁 L4。三个参数缺省 ⇒ 行为与变更前**逐字一致**（成功轮不写该条目）。

        情景链的**时序相邻标注**（change 0202 / ADR-0192）：``causal_links`` 开启且本会话有
        前一**已记忆**轮时，失败条目 ``tags`` 追加 ``after:<前序 trace_id>`` —— 语义是**时序相邻**、
        **不是因果**（故用机制本名而非 ``caused_by:``）。前序取自 ``self._last_trace``（**零记忆读**
        ⇒ 零新副作用），并在本方法末尾登记本轮 ⇒ 全流程**一个维护点**。缺省关 ⇒ 标签逐字不变。
        """
        if not trajectory or self._memory is None:
            return
        lines = [line for item in trajectory if (line := _trajectory_line(item))]
        if not lines:
            return
        self._memory.write(
            "L2",
            MemoryEntry(
                id=f"loop.{trace_id}",
                layer="L2",
                content=redact_secrets("\n".join(lines))[:_MAX_MEMORY_ENTRY],
                tags=["loop", "trajectory"],
                source=self._source,
                trace_id=trace_id,
                session_id=session_id,
            ),
        )
        if steps:
            sequence = "\n".join(redact_secrets(step) for step in steps)[:_MAX_MEMORY_ENTRY]
            self._memory.write(
                "L2",
                MemoryEntry(
                    id=f"loop.steps.{trace_id}",
                    layer="L2",
                    content=sequence,
                    tags=["loop", "steps"],
                    source=self._source,
                    trace_id=trace_id,
                    session_id=session_id,
                ),
            )
        if failed:
            tags = ["loop", "failure"]
            previous = self._last_trace.get(session_id, "")
            if self._causal_links and previous:
                tags.append(f"after:{previous}")
            self._memory.write(
                "L2",
                MemoryEntry(
                    id=f"loop.failure.{trace_id}",
                    layer="L2",
                    content=failure_digest(trajectory, steps, reason=reason, task=task),
                    tags=tags,
                    source=self._source,
                    trace_id=trace_id,
                    session_id=session_id,
                    kind="episodic",
                ),
            )
        # 前序登记在**末尾**（标注用的是**上一**轮）⇒ 「上一已记忆轮」口径由此钉死；
        # 零 I/O 零效应，故不受 `causal_links` 门控（只有标签的**写入**受门控）。
        self._last_trace[session_id] = trace_id

    def rollback(self, trace_id: str) -> None:
        if self._tools is not None:
            self._tools.rollback(trace_id)

    def decline(self, action: Action) -> Action:
        return Action(args={"reply": "已拒绝：动作需人工审批或校验未通过，本轮终止。"})

    # ---- 内部辅助 ----

    def _echo(self, ctx: LoopContext) -> str:
        if not ctx.messages:
            return "已完成："
        first = ctx.messages[0]
        if isinstance(first, dict):
            content = str(cast(dict[str, Any], first).get("content", ""))
        else:
            content = str(first)
        return f"已完成：{content}"

    def _window_plan(self, *, tiered: bool) -> WindowPlan:
        """三层滑窗配额（承 ``context.plan_window``；change 0178 / ADR-0169）。

        预算关闭（``token_budget <= 0``）⇒ 只按 ``history_turns`` 上界（``short_tokens=0`` 即
        「不按 token 截断」，逐字既有语义），不套用 ``plan_window`` 的「预算非正 ⇒ 关闭回灌」
        缺省 —— 否则预算关闭会误关回灌。
        """
        if self._token_budget > 0:
            return plan_window(self._history_turns, self._token_budget // 2, tiered=tiered)
        return WindowPlan(max(0, self._history_turns), 0, 0, 0)

    def _load_summaries(self, session_id: str) -> tuple[str, str]:
        """本会话的（长期摘要, 中期摘要）文本（缺省空 ⇒ 不注入；change 0178 / ADR-0169）。

        门控只按**本职**判据：未注入转录 / 未注入 memory / 空标识 ⇒ ``("", "")``。
        **不**受历史回放开关连坐 —— ``loop.history_turns`` 是**原文回灌**的轮数上界，
        与摘要通道解耦（change 0194 / ADR-0184）：`history_turns=0` 时历史带为空，
        但该会话已有的摘要 SHALL 照常注入。读取失败降级为空（不回灌摘要），不阻断本轮。
        """
        if self._transcript is None or self._memory is None or not session_id:
            return "", ""
        try:
            long_entry = self._memory.summary_for(session_id)
            mid_entry = self._memory.mid_summary_for(session_id)
        except Exception as err:  # noqa: BLE001 — 摘要读失败降级，本轮不回灌摘要
            warnings.warn(f"摘要读取失败，本轮不回灌摘要: {err}", RuntimeWarning, stacklevel=2)
            return "", ""
        return (
            long_entry.content if long_entry is not None else "",
            mid_entry.content if mid_entry is not None else "",
        )

    def _load_history(self, session_id: str, *, plan: WindowPlan) -> list[Any]:
        """本会话最近历史 —— 三层滑窗的**短带**（change 0178 / ADR-0169）。

        ``plan.mid_turns <= 0`` ⇒ 与既有「双重上界」（`history_turns` 轮 + 独立 token 切片）
        **逐字等价**（走 `tail`）；分层激活时改走 `window()` 取短带原文，中带由中期摘要承接。
        空标识 / 未注入转录 / 关闭回灌（`plan.short_turns <= 0`）⇒ 空。
        转录异常一律降级为空历史（不回灌），不阻断本轮。
        """
        if self._transcript is None or not session_id or plan.short_turns <= 0:
            return []
        try:
            if plan.mid_turns <= 0:
                rows = self._transcript.tail(
                    session_id, plan.short_turns, max_tokens=plan.short_tokens
                )
            else:
                rows, _ = self._transcript.window(
                    session_id,
                    short_turns=plan.short_turns,
                    mid_turns=plan.mid_turns,
                    short_tokens=plan.short_tokens,
                )
        except Exception as err:  # noqa: BLE001 — 转录读失败降级，本轮不回灌
            warnings.warn(f"转录读取失败，本轮不回灌历史: {err}", RuntimeWarning, stacklevel=2)
            return []
        return rows

    def _append_transcript(self, session_id: str, role: str, content: str) -> None:
        """追加一条转录；空标识 / 未注入转录 ⇒ 不落盘。

        独立于 `remember`（后者失败**不影响**已落盘的会话历史）；写失败降级不阻断本轮。
        """
        if self._transcript is None or not session_id:
            return
        try:
            self._transcript.append(session_id, role, content)
        except Exception as err:  # noqa: BLE001 — 转录落盘失败降级，不阻断本轮
            warnings.warn(f"转录写入失败: {err}", RuntimeWarning, stacklevel=2)

    def _start_trace(self, task_id: str) -> str:
        """开轮取 trace_id：经注入的 tracer 建链（其 id 贯穿全链路）。

        缺省未注入 tracer 时回退本地生成 id，行为与既有一致。
        """
        if self._tracer is None:
            return uuid.uuid4().hex
        return self._tracer.start_trace(task_id)

    def _end_trace(self, trace_id: str) -> None:
        """收尾**封口**本轮 trace（交付导出器 + 释放内存）；缺省未注入 tracer 则不做。

        调用点 SHALL 在 trace 完成回调**之后**：回调须能完整回放本轮事件。
        """
        if self._tracer is None:
            return
        self._tracer.end_trace(trace_id)

    def _trace(
        self,
        trace_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        module_id: str | None = None,
    ) -> None:
        if self._tracer is None:
            return
        self._tracer.record(
            TraceEvent(
                trace_id=trace_id,
                span_id=uuid.uuid4().hex,
                ts=time.time(),
                kind=kind,
                payload=payload or {},
                module_id=module_id,
            )
        )

    def _log_tool_call(
        self,
        trace_id: str,
        action: Action,
        result: ActionResult,
        *,
        latency_ms: float,
        output: str,
    ) -> None:
        """非终止动作完成后**另行**产出工具调用遥测（``kind="tool_call"``；缺省不产）。

        与 ``action_completed`` 事件**同判据、同点、同载荷**（参数/输出复用节选函数 ⇒ 事件面
        有界）：loop 是**唯一**同时持有「动作 + 执行结果 + 耗时」的位置，工具调用通道由此在
        **生产**有输入（消费侧 ``EvolutionWorker._to_traces`` 此前只有纸面通道）。
        经 ``TraceLogger.log_tool_call`` 产出而非直接写事件，避免载荷形状两处漂移。
        """
        if self._trace_logger is None:
            return
        self._trace_logger.log_tool_call(
            trace_id,
            action.tool_id,
            _args_excerpt(action.args),
            {"ok": not result.failed, "output": output},
            float(latency_ms),
        )

    async def _allow(self, action: Action) -> bool:
        decision = self._gate.confirm(
            action.tool_id, action.args, self._coeffects(action.tool_id), reversible=False
        )
        if decision.action != "auto":
            # 需确认：经审批通道询问人工；无通道或被拒即拒绝（fail-closed）
            if decision.action == "confirm" and self._approver is not None:
                return await self._approver(action.tool_id, action.args, decision.reason)
            return False
        if self._router is None:
            return True
        chosen = self._router.choose(
            {"tool_id": action.tool_id, "args": action.args},
            ["proceed", "block"],
        )
        return not self._chose_block(chosen)

    @staticmethod
    def _chose_block(result: DecisionResult) -> bool:
        answer = result.answers.get("choice")
        if not isinstance(answer, dict):
            return False
        return cast(dict[str, Any], answer).get("choice") == "block"

    def _coeffects(self, tool_id: str) -> list[str]:
        if self._tools is None:
            return []
        return (
            [t.coeffects for t in self._tools.active_tools() if t.tool_id == tool_id][0]
            if any(t.tool_id == tool_id for t in self._tools.active_tools())
            else []
        )

    def _apply_middlewares(self, ctx: LoopContext, action: Action) -> Action:
        for middleware in self._middlewares:
            decided = middleware(ctx, action)
            if decided is None:
                return self.decline(action)
            action = decided
        return action

    def _notify_action_result(
        self, ctx: LoopContext, action: Action, result: ActionResult, trace_id: str
    ) -> None:
        """结果侧观察者：非终止动作完成后按注册序回调；异常降级留痕、不改本轮结局。"""
        if action.is_terminal or not self._action_observers:
            return
        for observer in self._action_observers:
            try:
                observer(ctx, action, result)
            except Exception as err:  # noqa: BLE001 — 观察者失败降级不中断本轮
                self._trace(trace_id, "action_observer_failed", {"error": str(err)})
