"""loop 单元测试（对齐 §14 契约 + M2 验收锚点）。

覆盖：停止条件退出 / 单轮失败回滚 / 中间件被拒短路 / 循环与 token 超限 /
同步异步等价 / 端到端冒烟（loop 驱动 tool-use + memory）。
"""

from __future__ import annotations

import asyncio

from core.loop import Action, DefaultLoop
from core.memory import MemoryStore
from core.plugin_registry import CoeffectResolver
from core.tools import Tool, ToolDef, ToolProvider


def _echo_tool() -> Tool:
    return Tool(
        definition=ToolDef(
            tool_id="tools.echo",
            description="echo",
            schema={"type": "object", "properties": {"text": {"type": "string"}}},
            coeffects=[],
            reversible=True,
        ),
        handler=lambda text: f"echo:{text}",
    )


class _SpyProvider(ToolProvider):
    """记录回滚调用，验证单轮失败触发回滚。"""

    def __init__(self) -> None:
        super().__init__()
        self.rolled_back: list[str | None] = []

    def rollback(self, trace_id: str | None = None):
        self.rolled_back.append(trace_id)
        return super().rollback(trace_id)


# ---- 终端动作 ----


def test_run_terminal_reply() -> None:
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "你好"}))
    result = loop.run("问题")
    assert result.reply == "你好"
    assert result.trace_id


# ---- 中间件短路 ----


def test_middleware_reject_short_circuits() -> None:
    def planner(ctx):
        return Action(tool_id="tools.echo", args={"text": "hi"})

    loop = DefaultLoop(planner=planner, middlewares=[lambda ctx, action: None], max_rounds=3)
    result = loop.run("hi")
    assert result.reply.startswith("已拒绝")


# ---- 循环 / token 超限 ----


def test_max_rounds_limit() -> None:
    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.echo", args={"text": "x"}), max_rounds=2
    )
    result = loop.run("hi")
    assert "LOOP_LIMIT_EXCEEDED" in result.reply


def test_token_budget_limit() -> None:
    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.echo", args={"text": "x"}), token_budget=1
    )
    result = loop.run("hi")
    assert "TOKEN_BUDGET_EXCEEDED" in result.reply


# ---- 单轮失败回滚 ----


def test_single_round_failure_rolls_back() -> None:
    provider = _SpyProvider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.fail",
                description="",
                schema={"type": "object"},
                coeffects=["filesystem:write"],  # 未注册 → CoeffectMissing → 本轮失败
                reversible=False,
            ),
            handler=lambda: "x",
        )
    )

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.fail", args={})
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, tools=provider, max_rounds=5)
    result = loop.run("hi")
    assert result.reply == "done"
    assert provider.rolled_back  # 单轮失败触发回滚


# ---- 同步 / 异步等价 ----


def test_run_arun_equivalent() -> None:
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "ok"}))
    sync = loop.run("hi")
    async_result = asyncio.run(loop.arun("hi"))
    assert sync.reply == async_result.reply == "ok"
    assert sync.trace_id
    assert async_result.trace_id


# ---- 流式推理（逐 token reply_delta）----


class _StreamingPlanner:
    """duck-typed 流式 planner：先逐 delta 外发自然语言，末态产出终 Action。"""

    def __init__(self, deltas: list[str], action: Action) -> None:
        self._deltas = deltas
        self._action = action

    async def astream(self, ctx):
        for delta in self._deltas:
            yield delta
        yield self._action


def _collect_events(loop: DefaultLoop, prompt: str):
    async def _run():
        return [event async for event in loop.astream(prompt)]

    return asyncio.run(_run())


def test_astream_streaming_planner_yields_per_token_deltas() -> None:
    """流式 planner：推理期逐 token reply_delta，终态不重复全文。"""
    loop = DefaultLoop(planner=_StreamingPlanner(["你", "好"], Action(args={"reply": "你好"})))
    events = _collect_events(loop, "问题")
    deltas = [(e.type, e.payload) for e in events if e.type == "reply_delta"]
    assert deltas == [("reply_delta", {"text": "你"}), ("reply_delta", {"text": "好"})]
    assert events[-1].type == "loop_finished"
    assert events[-1].payload.reply == "你好"


def test_astream_non_streaming_planner_keeps_full_delta() -> None:
    """纯 callable planner：无 delta 时终态补一次全文（既有行为不变）。"""
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "ok"}))
    events = _collect_events(loop, "问题")
    deltas = [e for e in events if e.type == "reply_delta"]
    assert len(deltas) == 1 and deltas[0].payload == {"text": "ok"}


# ---- 端到端冒烟：loop 驱动 tool-use + memory ----


def test_e2e_loop_drives_tool_and_memory() -> None:
    provider = ToolProvider()
    provider.register(_echo_tool())
    memory = MemoryStore()

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "hi"})
        return Action(args={"reply": f"完成 {ctx.rounds} 步"})

    loop = DefaultLoop(planner=planner, tools=provider, memory=memory)
    result = loop.run("hello")
    assert result.reply == "完成 1 步"
    assert result.trace_id
    # 记忆写入：remember 落 L2 轨迹，按 trace 可审计
    assert memory.audit(result.trace_id) != []


def test_remember_stores_readable_reply_not_dict_repr() -> None:
    """remember 落 L2 的正文含终态回复语义，且无 dict repr 噪声（F7）。"""
    provider = ToolProvider()
    provider.register(_echo_tool())
    memory = MemoryStore()

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "hi"})
        return Action(args={"reply": "季度总结已完成"})

    loop = DefaultLoop(planner=planner, tools=provider, memory=memory)
    result = loop.run("q")
    entries = memory.audit(result.trace_id)
    assert entries and "季度总结已完成" in entries[0].content
    assert "'round'" not in entries[0].content


def test_loop_feeds_observation_back_to_planner() -> None:
    """观察回灌：工具轮的调用与执行结果进入下一轮 planner 上下文（ReAct 多轮前提）。"""
    provider = ToolProvider()
    provider.register(_echo_tool())
    seen: list[list] = []

    def planner(ctx):
        seen.append(list(ctx.messages))
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "hi"})
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, tools=provider)
    result = loop.run("q")
    assert result.reply == "done"
    roles = [m["role"] for m in seen[1]]  # type: ignore[index]
    assert roles == ["user", "assistant", "tool"]
    assert "tools.echo" in seen[1][1]["content"]  # type: ignore[index]
    assert "echo:hi" in seen[1][2]["content"]  # type: ignore[index]


# ---- 不可逆动作审批通道 ----


def _irreversible_echo_provider(executed: list[str]) -> ToolProvider:
    """带不可逆写 echo 工具的 provider（filesystem:write + irreversible）。"""
    resolver = CoeffectResolver()
    resolver.register("filesystem:write", True)
    provider = ToolProvider(coeffect_resolver=resolver)

    def handler(text: str) -> str:
        executed.append(text)
        return f"wecho:{text}"

    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.wecho",
                description="不可逆写 echo",
                schema={"type": "object", "properties": {"text": {"type": "string"}}},
                coeffects=["filesystem:write"],
                reversible=False,
            ),
            handler=handler,
        )
    )
    return provider


def test_irreversible_action_approval_allows_and_asks_once() -> None:
    """不可逆动作经审批通道单次询问（loop 问、provider 不重复），批准后执行。"""
    executed: list[str] = []
    provider = _irreversible_echo_provider(executed)
    asked: list[tuple[str, dict]] = []

    async def approver(tool_id: str, args: dict, reason: str) -> bool:
        asked.append((tool_id, args))
        return True

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.wecho", args={"text": "hi"}, is_irreversible=True)
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, tools=provider, approver=approver)
    result = loop.run("q")
    assert result.reply == "done"
    assert asked == [("tools.wecho", {"text": "hi"})]  # 单次询问，无双重提示
    assert executed == ["hi"]


def test_irreversible_action_rejected_declines_round() -> None:
    """审批被拒：动作不执行，本轮以已拒绝回复终止。"""
    executed: list[str] = []
    provider = _irreversible_echo_provider(executed)

    async def approver(tool_id: str, args: dict, reason: str) -> bool:
        return False

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.wecho", args={"text": "hi"}, is_irreversible=True)
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, tools=provider, approver=approver)
    result = loop.run("q")
    assert result.reply.startswith("已拒绝")
    assert executed == []


def test_irreversible_action_without_approver_fail_closed() -> None:
    """无审批通道：不可逆动作默认拒绝（fail-closed），不执行。"""
    executed: list[str] = []
    provider = _irreversible_echo_provider(executed)

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.wecho", args={"text": "hi"}, is_irreversible=True)
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, tools=provider)
    result = loop.run("q")
    assert result.reply.startswith("已拒绝")
    assert executed == []


def test_perceive_does_not_retrieve_memory() -> None:
    """检索归属 ContextEngine.assemble；perceive 只观察，不做记忆检索（架构图 :117）。"""

    class _SpyMemory:
        def __init__(self) -> None:
            self.reads: list[tuple[str, int]] = []

        def read(self, query: str, budget: int = 0) -> list[object]:
            self.reads.append((query, budget))
            return [{"source": "s", "content": "c"}]

        # 无 write：perceive 若试图写记忆会 AttributeError 直接暴露

    spy = _SpyMemory()
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "ok"}), memory=spy)  # type: ignore[arg-type]
    ctx = loop.perceive("查询内容")
    assert spy.reads == [], "perceive 不应触发 MemoryStore.read"
    assert not hasattr(ctx, "memory"), "LoopContext.memory 遗留字段已移除（A1）"


# ---- 工具动作事件（action_started / action_completed，spec：异步流式执行） ----


def test_astream_tool_action_events_order_and_payload() -> None:
    """非终止动作：执行前后产出 action_started/completed，先于该轮 step_completed。"""
    provider = ToolProvider()
    provider.register(_echo_tool())

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "hi"})
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, tools=provider, max_rounds=5)

    events = _collect_events(loop, "hi")

    # round0 工具轮（动作事件先于该轮 step_completed）+ round1 终止轮
    assert [e.type for e in events] == [
        "loop_started",
        "action_started",
        "action_completed",
        "step_completed",
        "step_completed",
        "reply_delta",
        "loop_finished",
    ]
    started = events[1].payload
    assert started["tool_id"] == "tools.echo"
    assert started["args"] == {"text": "hi"}
    assert started["round"] == 0
    completed = events[2].payload
    assert completed["tool_id"] == "tools.echo"
    assert completed["ok"] is True
    assert completed["duration_ms"] >= 0
    assert "echo:hi" in completed["output"]


def test_astream_terminal_action_emits_no_action_events() -> None:
    """终止动作（空 tool_id，回复收尾）不产出动作事件。"""
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "你好"}))

    events = _collect_events(loop, "hi")

    # 终止动作不发动作事件；step_completed 为每轮既有语义（含终止轮）
    assert [e.type for e in events] == [
        "loop_started",
        "step_completed",
        "reply_delta",
        "loop_finished",
    ]


def test_astream_failed_action_completes_with_ok_false() -> None:
    """失败动作：action_completed.ok=False、output 含错误信息（动作行仍收尾不挂起）。"""
    provider = ToolProvider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.fail",
                description="",
                schema={"type": "object"},
                coeffects=["filesystem:write"],  # 未注册 → CoeffectMissing → 失败
                reversible=False,
            ),
            handler=lambda: "x",
        )
    )

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.fail", args={"cmd": "boom"})
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, tools=provider, max_rounds=5)

    events = _collect_events(loop, "hi")

    kinds = [e.type for e in events]
    assert kinds[:4] == ["loop_started", "action_started", "action_completed", "step_completed"]
    completed = events[2].payload
    assert completed["ok"] is False
    assert completed["output"]
