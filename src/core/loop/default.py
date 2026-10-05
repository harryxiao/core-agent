"""默认智能体循环实现（DefaultLoop）。

把「观察→推理→行动→记忆」串成单轮闭环：异步为主（arun/astream）、同步为
薄壳（run）；不可逆动作过确认门，失败按 trace 回滚；横切中间件按序执行、
被拒短路；循环次数 / token 预算超限即终止，达阈值时压实上下文与记忆
（含固化打分与遗忘归档）。

对应接口：doc/03-interfaces/loop-interface.md §1
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

from core.context import Compactor, ContextError
from core.judgment import DecisionResult, DecisionRouter
from core.memory import MemoryEntry, MemoryStore
from core.observability import TraceEvent, Tracer
from core.plugin_registry import Plugin
from core.tools import SafetyGate, ToolProvider

from .protocol import Action, ActionResult, LoopContext, LoopEvent, LoopResult

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

# trace 完成回调：本轮遥测记录完毕后按**轮**提交 trace_id（登记一条已完成 trace）；缺省不做。
# 与冷路径回调**节律不同**（不随维护节拍节流）；loop 不 import evolution（架构红线），
# 生产侧注入组合根闭包（内部调 EvolutionWorker.on_trace_complete）。
TraceObserver = Callable[[str], None]

# 结果侧观察者：每个非终止动作完成后回调（上下文, 动作, 执行结果）→ 无返回值；仅通知，
# 单个观察者异常降级留痕、不改本轮结局。loop 不 import constraints（架构红线），
# 生产侧注入组合根适配层闭包。
ActionObserver = Callable[[LoopContext, Action, ActionResult], None]


_MAINTENANCE_INTERVAL_S = 900.0  # 记忆维护节拍（秒）：默认 15 分钟
_MAX_ACTION_EXCERPT = 400  # 动作事件 args/output 节选上界（事件面有界）


def _args_excerpt(args: dict[str, Any]) -> dict[str, Any] | str:
    """动作参数节选：短载荷原样（结构化消费友好），长载荷 str 化截断。"""
    text = str(args)
    if len(text) <= _MAX_ACTION_EXCERPT:
        return args
    return text[:_MAX_ACTION_EXCERPT]


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
    """行动/结果序列：首条 user 消息之后的上下文消息（助手动作 + 工具观察）逐条渲染。"""
    return [
        f"{message.get('role', '')}: {message.get('content', '')}" for message in ctx.messages[1:]
    ]


def _output_excerpt(value: Any) -> str:
    """动作输出节选：str 化截断（失败时 error，成功时 data）。"""
    return str(value or "")[:_MAX_ACTION_EXCERPT]


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
        cold_path: ColdPath | None = None,
        trace_observer: TraceObserver | None = None,
        max_rounds: int = 10,
        token_budget: int = 65536,
        maintenance_interval: float = _MAINTENANCE_INTERVAL_S,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._planner = planner
        self._memory = memory
        self._tools = tools
        self._gate = gate if gate is not None else SafetyGate()
        self._middlewares = list(middlewares or [])
        self._action_observers = list(action_observers or [])
        self._tracer = tracer
        self._router = router
        self._approver = approver
        self._compactor = compactor
        self._turn_observer = turn_observer
        self._notes_consult = notes_consult
        self._cold_path = cold_path
        self._trace_observer = trace_observer
        self._max_rounds = max_rounds
        self._token_budget = token_budget
        self._maintenance_interval = maintenance_interval
        self._clock = clock if clock is not None else time.monotonic
        self._last_maintenance = self._clock()

    # ---- Plugin 生命周期 ----

    def set_limits(self, *, max_rounds: int | None = None, token_budget: int | None = None) -> None:
        """运行期改预算上限（``None`` = 保持该项；change `0099`）。

        两值在每轮判定处读取 ⇒ 赋值即**下一轮**生效，无需重建循环。
        合法性由配置层把关（此处不重复校验）。
        """
        if max_rounds is not None:
            self._max_rounds = max_rounds
        if token_budget is not None:
            self._token_budget = token_budget

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
        reply = ""
        trace_id = ""
        failed = False
        async for event in self.astream(user_input, session_id=session_id):
            if event.type == "loop_started":
                trace_id = str(event.payload.get("trace_id", ""))
            elif event.type == "loop_finished":
                return event.payload
            elif event.type == "loop_failed":
                reply = str(event.payload.get("reason", "LOOP_FAILED"))
                failed = True
        return LoopResult(reply=reply, trace_id=trace_id, failed=failed)

    async def _reason_events(self, ctx: LoopContext) -> AsyncIterator[LoopEvent | Action]:
        """推理步事件流：planner 支持流式时逐 delta 转 reply_delta，末态产出 Action。

        planner 无 ``astream``（含 None/纯 callable）时退化为 reason()，仅产出单个
        Action，事件序与非流式实现完全一致。
        """
        planner = getattr(self._planner, "astream", None)
        if planner is None:
            yield await self.reason(ctx)
            return
        async for item in planner(ctx):
            if isinstance(item, str):
                yield LoopEvent("reply_delta", {"text": item})
            else:
                yield item

    async def astream(  # noqa: C901 — 主管线多分支长管道（事件面七类）
        self, user_input: str, *, session_id: str = ""
    ) -> AsyncIterator[LoopEvent]:
        trace_id = self._start_trace(user_input)
        yield LoopEvent("loop_started", {"trace_id": trace_id})
        self._trace(trace_id, "loop_started", {"trace_id": trace_id})
        ctx = self.perceive(user_input)
        self._consult_notes(ctx, trace_id)
        limit_reason = ""
        streamed = False  # 本轮循环是否已流式外发 reply_delta（避免终态重复全文）
        while not ctx.done():
            if ctx.rounds >= self._max_rounds:
                limit_reason = "LOOP_LIMIT_EXCEEDED"
                break
            action: Action | None = None
            async for item in self._reason_events(ctx):
                if isinstance(item, LoopEvent):
                    streamed = True
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
            result = await self.act(action, trace_id, approved=approved)
            if not action.is_terminal:
                yield LoopEvent(
                    "action_completed",
                    {
                        "round": ctx.rounds,
                        "tool_id": action.tool_id,
                        "ok": not result.failed,
                        "duration_ms": int((time.monotonic() - act_t0) * 1000),
                        "output": _output_excerpt(result.error if result.failed else result.data),
                    },
                )
            self._notify_action_result(ctx, action, result, trace_id)
            self._record_observation(ctx, action, result)
            if result.failed:
                self.rollback(trace_id)
            ctx = self.observe(ctx, result)
            yield LoopEvent("step_completed", {"round": ctx.rounds, "failed": result.failed})
            self._trace(trace_id, "step_completed", {"round": ctx.rounds, "failed": result.failed})
            if self._should_compact(ctx):
                self._compact(ctx, trace_id)
            if self._token_budget > 0 and ctx.token_used >= self._token_budget:
                limit_reason = "TOKEN_BUDGET_EXCEEDED"
                break
        # 收尾钩子：成功/失败都提交（失败信号供技能迭代判据；SOP 提炼仍只吸收成功）
        self._notify_turn(ctx, trace_id, ok=not limit_reason)
        if limit_reason:
            ctx.reply = f"{limit_reason}: 本轮终止"
            yield LoopEvent("loop_failed", {"reason": limit_reason, "trace_id": trace_id})
        self.remember(trace_id, [*ctx.trajectory, {"reply": ctx.reply}], session_id=session_id)
        self._maintain(trace_id)
        self._trace(
            trace_id,
            "loop_finished",
            {"reply": ctx.reply, "failed": bool(limit_reason)},
            module_id="loop.default" if limit_reason else None,
        )
        # 本轮遥测已齐：交给 trace 完成回调（登记一条已完成 trace；缺省不启用）
        self._notify_trace_complete(trace_id)
        # 顺序约束：回调之后才封口（回调须能完整回放本轮事件；封口交付导出器 + 释放内存）
        self._end_trace(trace_id)
        if not streamed:  # 未流式外发过 delta 才补一次全文（非流式 planner 兼容路径）
            yield LoopEvent("reply_delta", {"text": ctx.reply})
        yield LoopEvent(
            "loop_finished",
            LoopResult(reply=ctx.reply, trace_id=trace_id, failed=bool(limit_reason)),
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

    def _maintain(self, trace_id: str) -> None:
        """收尾维护节拍：距上次维护达间隔才触发一次（含①记忆遗忘 ②冷路径机会），各自失败降级。

        间隔 ``<=0`` 关闭节拍；时钟经构造注入（可测）。维护作用于整个存储 / 冷路径状态，
        与会话无关，故节拍状态驻留实例（多会话共享一个节拍）。两件事**各自失败降级、不中断本轮**。
        """
        if self._maintenance_interval <= 0:
            return
        now = self._clock()
        if now - self._last_maintenance < self._maintenance_interval:
            return
        self._last_maintenance = now
        if self._memory is not None:
            try:
                self._memory.forget()
            except Exception as err:  # noqa: BLE001 — 遗忘失败降级，本轮继续
                self._trace(trace_id, "maintenance_failed", {"error": str(err)})
        if self._cold_path is not None:
            try:
                self._cold_path()
            except Exception as err:  # noqa: BLE001 — 冷路径失败降级，本轮继续
                self._trace(trace_id, "cold_path_failed", {"error": str(err)})

    def _should_compact(self, ctx: LoopContext) -> bool:
        """轮数或 token 预算达阈值即触发压实（未注入压实器则永不触发）。

        预算关闭（``token_budget <= 0``）时只按轮数维度判定，避免 ``token_used >= 0``
        恒真导致每轮压实。
        """
        if self._compactor is None:
            return False
        if self._token_budget <= 0:
            return self._compactor.should_compact(ctx.rounds, 0, 1)
        return self._compactor.should_compact(ctx.rounds, ctx.token_used, self._token_budget)

    def _compact(self, ctx: LoopContext, trace_id: str) -> None:
        """压实：多轮历史提炼沉淀（persist）→ 记忆固化（打分 + 会话摘要）→ 遗忘归档。

        三步共用一次触发、任一步**降级不中断本轮**（原记忆保持不变，失败经观测通道
        记 ``maintenance_failed`` 留痕）；终止语义不变：压实后仍按既有预算/轮数条件终止。
        """
        assert self._compactor is not None  # noqa: S101 — 调用点已判空
        try:
            self._compactor.persist(self._compactor.compact(ctx.messages))
        except ContextError:
            pass  # 无可沉淀关键信息：非错误，不替换原文
        except Exception as err:  # noqa: BLE001 — 压实失败降级，本轮继续
            self._trace(trace_id, "maintenance_failed", {"error": str(err)})
        if self._memory is None:
            return
        try:
            self._memory.compact()
        except Exception as err:  # noqa: BLE001 — 打分/摘要失败降级，原记忆不丢
            self._trace(trace_id, "maintenance_failed", {"error": str(err)})
        try:
            self._memory.forget()
        except Exception as err:  # noqa: BLE001 — 遗忘失败降级，本轮继续
            self._trace(trace_id, "maintenance_failed", {"error": str(err)})

    # ---- 阶段方法 ----

    def perceive(self, user_input: str) -> LoopContext:
        # 检索归 ContextEngine.assemble（架构图 :117）；perceive 只观察，不检索记忆。
        tools = self._tools.active_tools() if self._tools is not None else []
        return LoopContext(
            messages=[{"role": "user", "content": user_input}],
            tools=tools,
            token_used=len(user_input) // 4,
        )

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
            return ActionResult(failed=False, data=action.args)
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
        ctx.token_used += len(str(result.data)) // 4
        return ctx

    def remember(self, trace_id: str, trajectory: list[Any], *, session_id: str = "") -> None:
        """把本轮轨迹沉淀为 L2 记忆（无行动不记忆）。

        轨迹项渲染为可读行（轮次/成败/错误），末条 ``reply`` 提供可检索的语义内容；
        ``session_id`` 记入条目，供压实/固化/遗忘按会话归组（缺省空串 = 未归属）。
        """
        if not trajectory or self._memory is None:
            return
        lines = [line for item in trajectory if (line := _trajectory_line(item))]
        if not lines:
            return
        summary = "\n".join(lines)[:2048]
        self._memory.write(
            "L2",
            MemoryEntry(
                id=f"loop.{trace_id}",
                layer="L2",
                content=summary,
                tags=["loop", "trajectory"],
                source="loop",
                trace_id=trace_id,
                session_id=session_id,
            ),
        )

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
