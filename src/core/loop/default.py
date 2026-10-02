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

    async def astream(self, user_input: str) -> AsyncIterator[LoopEvent]:
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
            if action.is_irreversible and not self._allow(action):
                action = self.decline(action)
            result = await self.act(action, trace_id)
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
        self.remember(trace_id, ctx.trajectory)
        self._trace(trace_id, "loop_finished", {"reply": ctx.reply, "failed": bool(limit_reason)})
        if not streamed:  # 未流式外发过 delta 才补一次全文（非流式 planner 兼容路径）
            yield LoopEvent("reply_delta", {"text": ctx.reply})
        yield LoopEvent(
            "loop_finished",
            LoopResult(reply=ctx.reply, trace_id=trace_id, failed=bool(limit_reason)),
        )

    # ---- 阶段方法 ----

    def perceive(self, user_input: str) -> LoopContext:
        memory = self._memory.read("", budget=2048) if self._memory is not None else []
        tools = self._tools.active_tools() if self._tools is not None else []
        return LoopContext(
            messages=[{"role": "user", "content": user_input}],
            memory=memory,
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

    async def act(self, action: Action, trace_id: str) -> ActionResult:
        if action.is_terminal:
            return ActionResult(failed=False, data=action.args)
        if self._tools is None:
            return ActionResult(failed=True, error="NO_TOOL_PROVIDER")
        result = await self._tools.ainvoke(action.tool_id, action.args, trace_id=trace_id)
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
        if not trajectory or self._memory is None:
            return
        self._memory.write(
            "L2",
            MemoryEntry(
                id=f"loop.{trace_id}",
                layer="L2",
                content=f"轨迹 {trace_id}: {len(trajectory)} 步",
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

    def _allow(self, action: Action) -> bool:
        decision = self._gate.confirm(
            action.tool_id, action.args, self._coeffects(action.tool_id), reversible=False
        )
        if decision.action != "auto":
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
