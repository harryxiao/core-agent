"""默认智能体循环实现（DefaultLoop）。

把「观察→推理→行动→记忆」串成单轮闭环：异步为主（arun/astream）、同步为
薄壳（run）；不可逆动作过确认门，失败按 trace 回滚；横切中间件按序执行、
被拒短路；循环次数 / token 预算超限即终止。

对应接口：doc/03-interfaces/loop-interface.md §1
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

from core.memory import MemoryEntry, MemoryStore
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
        planner: Callable[[LoopContext], Action] | None = None,
        memory: MemoryStore | None = None,
        tools: ToolProvider | None = None,
        gate: SafetyGate | None = None,
        middlewares: list[Middleware] | None = None,
        max_rounds: int = 10,
        token_budget: int = 65536,
    ) -> None:
        self._planner = planner
        self._memory = memory
        self._tools = tools
        self._gate = gate if gate is not None else SafetyGate()
        self._middlewares = list(middlewares or [])
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

    async def astream(self, user_input: str) -> AsyncIterator[LoopEvent]:
        trace_id = uuid.uuid4().hex
        yield LoopEvent("loop_started", {"trace_id": trace_id})
        ctx = self.perceive(user_input)
        limit_reason = ""
        while not ctx.done():
            if ctx.rounds >= self._max_rounds:
                limit_reason = "LOOP_LIMIT_EXCEEDED"
                break
            action = self.reason(ctx)
            action = self._apply_middlewares(ctx, action)
            if action.is_irreversible and not self._allow(action):
                action = self.decline(action)
            result = await self.act(action, trace_id)
            if result.failed:
                self.rollback(trace_id)
            ctx = self.observe(ctx, result)
            yield LoopEvent("step_completed", {"round": ctx.rounds, "failed": result.failed})
            if self._token_budget > 0 and ctx.token_used >= self._token_budget:
                limit_reason = "TOKEN_BUDGET_EXCEEDED"
                break
        if limit_reason:
            ctx.reply = f"{limit_reason}: 本轮终止"
            yield LoopEvent("loop_failed", {"reason": limit_reason, "trace_id": trace_id})
        self.remember(trace_id, ctx.trajectory)
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

    def reason(self, ctx: LoopContext) -> Action:
        if self._planner is not None:
            return self._planner(ctx)
        return Action(args={"reply": self._echo(ctx)})

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

    def _allow(self, action: Action) -> bool:
        decision = self._gate.confirm(
            action.tool_id, action.args, self._coeffects(action.tool_id), reversible=False
        )
        return decision.action == "auto"

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
