"""默认智能体循环实现（DefaultLoop）。

把「观察→推理→行动→记忆」串成单轮闭环：异步为主（arun/astream）、同步为
薄壳（run）；不可逆动作过确认门，失败按 trace 回滚；横切中间件按序执行、
被拒短路；循环次数 / token 预算超限即终止。

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
        tracer: Tracer | None = None,
        router: DecisionRouter | None = None,
        approver: Approver | None = None,
        max_rounds: int = 10,
        token_budget: int = 65536,
    ) -> None:
        self._planner = planner
        self._memory = memory
        self._tools = tools
        self._gate = gate if gate is not None else SafetyGate()
        self._middlewares = list(middlewares or [])
        self._tracer = tracer
        self._router = router
        self._approver = approver
        self._max_rounds = max_rounds
        self._token_budget = token_budget

    # ---- Plugin 生命周期 ----

    def load(self) -> None:
        return None

    def unload(self) -> None:
        return None

    def check(self) -> bool:
        return True

    # ---- 三入口（异步为主、同步薄壳）----

    def run(self, user_input: str) -> LoopResult:
        return asyncio.run(self.arun(user_input))

    async def arun(self, user_input: str) -> LoopResult:
        reply = ""
        trace_id = ""
        failed = False
        async for event in self.astream(user_input):
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
        self, user_input: str
    ) -> AsyncIterator[LoopEvent]:
        trace_id = uuid.uuid4().hex
        yield LoopEvent("loop_started", {"trace_id": trace_id})
        self._trace(trace_id, "loop_started", {"trace_id": trace_id})
        ctx = self.perceive(user_input)
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
            self._record_observation(ctx, action, result)
            if result.failed:
                self.rollback(trace_id)
            ctx = self.observe(ctx, result)
            yield LoopEvent("step_completed", {"round": ctx.rounds, "failed": result.failed})
            self._trace(trace_id, "step_completed", {"round": ctx.rounds, "failed": result.failed})
            if self._token_budget > 0 and ctx.token_used >= self._token_budget:
                limit_reason = "TOKEN_BUDGET_EXCEEDED"
                break
        if limit_reason:
            ctx.reply = f"{limit_reason}: 本轮终止"
            yield LoopEvent("loop_failed", {"reason": limit_reason, "trace_id": trace_id})
        self.remember(trace_id, [*ctx.trajectory, {"reply": ctx.reply}])
        self._trace(trace_id, "loop_finished", {"reply": ctx.reply, "failed": bool(limit_reason)})
        if not streamed:  # 未流式外发过 delta 才补一次全文（非流式 planner 兼容路径）
            yield LoopEvent("reply_delta", {"text": ctx.reply})
        yield LoopEvent(
            "loop_finished",
            LoopResult(reply=ctx.reply, trace_id=trace_id, failed=bool(limit_reason)),
        )

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

    def remember(self, trace_id: str, trajectory: list[Any]) -> None:
        """把本轮轨迹沉淀为 L2 记忆（无行动不记忆）。

        轨迹项渲染为可读行（轮次/成败/错误），末条 ``reply`` 提供可检索的语义内容。
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

    def _trace(self, trace_id: str, kind: str, payload: dict[str, Any] | None = None) -> None:
        if self._tracer is None:
            return
        self._tracer.record(
            TraceEvent(
                trace_id=trace_id,
                span_id=uuid.uuid4().hex,
                ts=time.time(),
                kind=kind,
                payload=payload or {},
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
