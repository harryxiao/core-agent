"""loop 单元测试（对齐 §14 契约 + M2 验收锚点）。

覆盖：停止条件退出 / 单轮失败回滚 / 中间件被拒短路 / 循环与 token 超限 /
同步异步等价 / 端到端冒烟（loop 驱动 tool-use + memory）。
"""

from __future__ import annotations

import asyncio
import time

import pytest

from core.context import Compactor
from core.loop import Action, DefaultLoop, Thinking, current_session_id
from core.memory import MemoryEntry, MemoryStore
from core.observability import TraceEvent, Tracer
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


def _echo_provider() -> ToolProvider:
    provider = ToolProvider()
    provider.register(_echo_tool())
    return provider


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


def test_current_session_id_visible_in_act_and_reset_afterward() -> None:
    """动作期 ContextVar 携带会话标识；动作结束后复位（change 0247）。"""
    seen: list[str] = []

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "x"})
        return Action(args={"reply": "done"})

    def handler(text: str) -> str:
        seen.append(current_session_id.get())
        return f"echo:{text}"

    provider = ToolProvider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.echo",
                description="echo",
                schema={"type": "object", "properties": {"text": {"type": "string"}}},
                coeffects=[],
                reversible=True,
            ),
            handler=handler,
        )
    )
    loop = DefaultLoop(planner=planner, tools=provider)
    loop.run("q", session_id="sess-42")
    assert seen == ["sess-42"]
    assert current_session_id.get() == ""


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


# ---- 思考回显事件面（change 0145 / 账本 E58）----


class _ThinkingPlanner:
    """duck-typed 流式 planner：外发 `Thinking` 增量（+ 可选回复增量）后产终 Action。"""

    def __init__(self, items: list[object], action: Action) -> None:
        self._items = items
        self._action = action

    async def astream(self, ctx):
        for item in self._items:
            yield item
        yield self._action


def test_astream_thinking_planner_emits_loop_reasoning() -> None:
    """planner 外发 `Thinking` ⇒ 逐段转 `loop.reasoning`（与 `reply_delta` 类型相异）。"""
    loop = DefaultLoop(
        planner=_ThinkingPlanner(
            [Thinking("想"), Thinking("一下"), "好"], Action(args={"reply": "好"})
        )
    )
    events = _collect_events(loop, "问题")
    reasoning = [(e.type, e.payload) for e in events if e.type == "loop.reasoning"]
    deltas = [(e.type, e.payload) for e in events if e.type == "reply_delta"]
    assert reasoning == [
        ("loop.reasoning", {"text": "想", "round": 0}),
        ("loop.reasoning", {"text": "一下", "round": 0}),
    ]
    assert deltas == [("reply_delta", {"text": "好"})]
    assert events[-1].payload.reply == "好"


def test_astream_thinking_events_do_not_suppress_terminal_reply() -> None:
    """`streamed` 判据只认 `reply_delta`：仅思考事件不吞终态全文补发。"""
    loop = DefaultLoop(planner=_ThinkingPlanner([Thinking("想")], Action(args={"reply": "好"})))
    events = _collect_events(loop, "问题")
    deltas = [(e.type, e.payload) for e in events if e.type == "reply_delta"]
    assert deltas == [("reply_delta", {"text": "好"})]
    assert [e.type for e in events if e.type == "loop.reasoning"] == ["loop.reasoning"]


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


# ---- 结果侧观察者（change 0052 / E1）----


def _echo_action_loop(*, observers, tracer=None):
    provider = ToolProvider()
    provider.register(_echo_tool())

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "hi"})
        return Action(args={"reply": "ok"})

    return DefaultLoop(planner=planner, tools=provider, action_observers=observers, tracer=tracer)


def test_action_observers_called_in_order_with_result() -> None:
    calls: list[tuple[str, bool]] = []
    loop = _echo_action_loop(
        observers=[
            lambda ctx, action, result: calls.append((action.tool_id, result.failed)),
            lambda ctx, action, result: calls.append((action.tool_id, result.failed)),
        ]
    )
    loop.run("hi")
    assert calls == [("tools.echo", False), ("tools.echo", False)]


def test_action_observer_failure_degrades_without_breaking_round() -> None:
    tracer = _RecordingTracer()

    def boom(ctx, action, result):
        raise RuntimeError("observer boom")  # noqa: TRY003 — 测试用哨兵异常

    loop = _echo_action_loop(observers=[boom], tracer=tracer)
    result = loop.run("hi")
    assert result.reply == "ok"  # 本轮照常完成
    assert "action_observer_failed" in tracer.kinds


def test_terminal_action_skips_observers() -> None:
    calls: list[object] = []
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        action_observers=[lambda ctx, a, r: calls.append(a)],
    )
    loop.run("hi")
    assert calls == []


def test_middleware_can_rewrite_action() -> None:
    """回归：中间件改写动作（非拒绝）仍生效，改写后的参数抵达执行。"""
    received: list[dict] = []
    provider = ToolProvider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.rec",
                description="",
                schema={"type": "object"},
                coeffects=[],
                reversible=True,
            ),
            handler=lambda **kw: received.append(kw) or "ok",
        )
    )

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.rec", args={"text": "orig"})
        return Action(args={"reply": "done"})

    def rewrite(ctx, action):
        return Action(tool_id=action.tool_id, args={"text": "rewritten"})

    loop = DefaultLoop(planner=planner, tools=provider, middlewares=[rewrite])
    loop.run("hi")
    assert received == [{"text": "rewritten"}]


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


# ---- 压实触发（0041） ----


def _summary_memory() -> MemoryStore:
    """注入纯本地假摘要器：不触网的 memory（压实链路离线可验）。"""

    def summarizer(entries: list[MemoryEntry]) -> str:
        return "摘要：" + "；".join(e.content for e in entries)

    return MemoryStore(summarizer=summarizer)


def _prior_entry() -> MemoryEntry:
    return MemoryEntry(
        id="loop.prior",
        layer="L2",
        content="上一轮：结论 完成",
        tags=["loop"],
        source="loop",
        trace_id="prior",
        session_id="s1",
    )


def _compacting_loop(memory: MemoryStore, compactor: Compactor, **kwargs: object) -> DefaultLoop:
    provider = ToolProvider()
    provider.register(_echo_tool())

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "结论"})
        return Action(args={"reply": "done"})

    return DefaultLoop(
        planner=planner,
        tools=provider,
        memory=memory,
        compactor=compactor,
        max_rounds=3,
        **kwargs,  # type: ignore[arg-type]
    )


def test_loop_compaction_persists_history_and_summarizes_prior_memory() -> None:
    memory = _summary_memory()
    memory.write("L2", _prior_entry())
    loop = _compacting_loop(memory, Compactor(memory=memory, step_threshold=1))

    loop.run("hi")

    entries = {e.id: e for e in memory.audit()}
    summary = entries.get("compaction.summary.s1")
    assert summary is not None, "轮数达阈值 → 触发压实，历史 episodic 提炼为 semantic 摘要"
    assert summary.kind == "semantic" and "from:loop.prior" in summary.tags
    assert "compaction.fact.default.0" in entries, "上下文压实产物同批落 L2（persist）"
    assert entries["compaction.fact.default.0"].kind == "semantic"
    assert dict(memory.index().entries)["loop.prior"] == "L4", "被摘要的原条目归档 L4"


def test_loop_compaction_triggers_on_token_budget_and_degrades() -> None:
    """预算触顶 ⇒ 先压实并给一轮收尾；收尾轮完成 ⇒ 正常收口（change 0230 / G2）。"""
    memory = _summary_memory()
    memory.write("L2", _prior_entry())
    loop = _compacting_loop(memory, Compactor(memory=memory, step_threshold=100), token_budget=1)

    result = loop.run("hi")

    assert result.reply == "done", "收尾轮完成 ⇒ 不被 TOKEN_BUDGET_EXCEEDED 覆盖"
    assert "compaction.summary.s1" in {e.id for e in memory.audit() if e.kind == "semantic"}


def test_budget_overflow_without_compactor_terminates_immediately() -> None:
    """未注入压实器 ⇒ 无降级路径，立即终止（既有行为不变）。"""
    calls: list[int] = []

    def planner(ctx):
        calls.append(ctx.rounds)
        return Action(tool_id="tools.echo", args={"text": "x"})

    loop = DefaultLoop(planner=planner, tools=_echo_provider(), token_budget=1, max_rounds=5)
    result = loop.run("hi")

    assert "TOKEN_BUDGET_EXCEEDED" in result.reply
    assert len(calls) == 1, "无压实器 ⇒ 不额外执行收尾轮"


def test_budget_overflow_terminates_after_one_grace_round() -> None:
    """收尾轮仍未完成 ⇒ 至多一轮降级后终止（不无限重试）。"""
    calls: list[int] = []

    def planner(ctx):
        calls.append(ctx.rounds)
        return Action(tool_id="tools.echo", args={"text": "x"})

    memory = _summary_memory()
    loop = DefaultLoop(
        planner=planner,
        tools=_echo_provider(),
        memory=memory,
        compactor=Compactor(memory=memory, step_threshold=100),
        token_budget=1,
        max_rounds=5,
    )
    result = loop.run("hi")

    assert "TOKEN_BUDGET_EXCEEDED" in result.reply
    assert len(calls) == 2, "预算触顶后恰好给一轮收尾，随后终止"  # noqa: PLR2004


def _round_episodic(entry_id: str, session: str) -> MemoryEntry:
    """本轮 L2 事件条目（含结论提示词 ⇒ 会被压实聚合）。"""
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=f"{entry_id} 结论 完成",
        tags=["loop"],
        source="loop",
        trace_id="prior",
        session_id=session,
        kind="episodic",
    )


def test_loop_compaction_scopes_memory_to_round_session() -> None:
    """轮内压实的记忆固化按本轮会话收窄：他会话条目层级不变（change 0192）。"""
    memory = _summary_memory()
    memory.write("L2", _round_episodic("a.0", "s1"))
    memory.write("L2", _round_episodic("b.0", "s2"))
    loop = _compacting_loop(memory, Compactor(memory=memory, step_threshold=1))

    loop.run("hi", session_id="s1")

    index = dict(memory.index().entries)
    assert index["a.0"] == "L4", "本轮会话条目被聚合归档"
    assert index["b.0"] == "L2", "他会话条目 SHALL NOT 被顺手聚合（变更前为跨会话串扰）"


def test_loop_compaction_persist_trace_is_session_keyed() -> None:
    """轮内压实产物 trace 携带会话键（change 0192）：非常量 `compaction`。"""
    memory = _summary_memory()
    loop = _compacting_loop(memory, Compactor(memory=memory, step_threshold=1))

    loop.run("hi", session_id="s1")

    facts = [e for e in memory.audit() if e.id.startswith("compaction.fact.")]
    assert facts, "本轮含结论提示词 ⇒ 上下文压实产生产物"
    assert {e.trace_id for e in facts} == {"compaction.s1"}, "产物 trace SHALL 携带会话键"


def test_loop_without_compactor_does_not_compact() -> None:
    memory = _summary_memory()
    memory.write("L2", _prior_entry())
    provider = ToolProvider()
    provider.register(_echo_tool())
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}), tools=provider, memory=memory
    )

    loop.run("hi")

    assert [e for e in memory.audit() if e.kind == "semantic"] == []
    assert dict(memory.index().entries)["loop.prior"] == "L2"


def test_loop_compaction_not_triggered_when_budget_disabled() -> None:
    """token 预算关闭（<=0）时不因 token 维度触发，仅轮数维度有效。"""
    memory = _summary_memory()
    memory.write("L2", _prior_entry())
    loop = _compacting_loop(memory, Compactor(memory=memory, step_threshold=100), token_budget=0)

    loop.run("hi")

    assert [e for e in memory.audit() if e.kind == "semantic"] == []


def test_loop_forgetting_archives_stale_entries_on_compaction() -> None:
    """压实触发顺带遗忘：陈旧零复用条目迁 L4，高复用条目不受影响。"""
    memory = MemoryStore()  # 无摘要器：隔离遗忘这一步
    stale = _prior_entry()
    stale.ts = time.time() - 30 * 86400.0
    warm = _prior_entry()
    warm.id = "loop.warm"
    warm.ts = stale.ts
    warm.reuse_count = 10
    memory.write("L2", stale)
    memory.write("L2", warm)
    loop = _compacting_loop(memory, Compactor(memory=memory, step_threshold=1))

    loop.run("hi")

    layers = dict(memory.index().entries)
    assert layers["loop.prior"] == "L4", "压实触发 → 顺带遗忘陈旧低分条目"
    assert layers["loop.warm"] == "L2", "高复用条目不被遗忘"
    assert "loop.prior" in {e.id for e in memory.audit()}, "归档不删除，仍可审计"


# ---- SOP 收尾钩子（0043） ----


class _RecordingTracer:
    """记录事件 kind，验证降级留痕；并满足收尾封口的生命周期面（change 0103）。"""

    def __init__(self) -> None:
        self.kinds: list[str] = []

    def start_trace(self, _task_id: str) -> str:
        return "trace-stub"

    def end_trace(self, _trace_id: str) -> None:
        return None

    def record(self, event) -> None:  # noqa: ANN001
        self.kinds.append(event.kind)


class _CapturingExporter:
    """收集封口交付的事件（落盘真路径的桩，change 0103）。"""

    def __init__(self) -> None:
        self.batches: list[list[TraceEvent]] = []

    def emit(self, events: list[TraceEvent]) -> None:
        self.batches.append(list(events))

    @property
    def events(self) -> list[TraceEvent]:
        return [event for batch in self.batches for event in batch]


def test_loop_fires_turn_observer_on_success() -> None:
    seen: list[tuple[str, list[str], bool, str]] = []
    provider = ToolProvider()
    provider.register(_echo_tool())

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "结论"})
        return Action(args={"reply": "done"})

    loop = DefaultLoop(
        planner=planner,
        tools=provider,
        max_rounds=3,
        turn_observer=lambda task, steps, ok, reply: seen.append((task, steps, ok, reply)),
    )

    loop.run("整理会议纪要")

    assert len(seen) == 1, "成功收尾触发一次"
    task, steps, ok, reply = seen[0]
    assert ok is True, "成功轮 ok=True"
    assert task == "整理会议纪要", "钩子拿到任务文本"
    assert any("tools.echo" in step for step in steps), "行动/结果序列承载工具调用"
    assert reply == "done", "钩子拿到最终回复（沉淀提炼的输入）"


def test_loop_fires_turn_observer_on_failure() -> None:
    seen: list[tuple[str, list[str], bool]] = []
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "unused"}),
        max_rounds=0,
        turn_observer=lambda task, steps, ok, reply: seen.append((task, steps, ok)),
    )

    result = loop.run("超限任务")

    assert result.failed, "轮数超限 → 本轮失败"
    assert len(seen) == 1 and seen[0][2] is False, "失败轮也提交（ok=False，供反馈判定）"


def test_loop_turn_observer_error_does_not_break_round() -> None:
    tracer = _RecordingTracer()

    def boom(task: str, steps: list[str], ok: bool, reply: str) -> None:
        raise RuntimeError("观察者不可用")  # noqa: TRY003

    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        tracer=tracer,
        turn_observer=boom,
    )

    result = loop.run("任务")

    assert not result.failed and result.reply == "done", "钩子抛错不影响本轮结果"
    assert "turn_observer_failed" in tracer.kinds, "钩子抛错降级留痕"


# ---- 会话标识随记忆沉淀落账（spec：执行循环「记忆沉淀携带会话标识」） ----


class _RecordingMemory:
    """记录写入条目的记忆替身（只关心沉淀结果）。"""

    def __init__(self) -> None:
        self.written: list[MemoryEntry] = []

    def read(self, query: str, budget: int = 0) -> list[MemoryEntry]:
        return []

    def write(self, layer: str, entry: MemoryEntry) -> str:
        self.written.append(entry)
        return entry.id


def test_memory_carries_session_id() -> None:
    """会话标识随调用传递并写入 L2 条目（不驻留循环实例）。"""
    memory = _RecordingMemory()
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "done"}), memory=memory)  # type: ignore[arg-type]
    loop.run("任务", session_id="s-1")
    assert [entry.session_id for entry in memory.written] == ["s-1"]


def test_memory_session_defaults_empty() -> None:
    """未指定会话标识时归缺省空串分组（与既有语义兼容）。"""
    memory = _RecordingMemory()
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "done"}), memory=memory)  # type: ignore[arg-type]
    loop.run("任务")
    assert [entry.session_id for entry in memory.written] == [""]


def test_thinking_only_visible_through_reasoning_event() -> None:
    """思考原文仅经 `loop.reasoning` 可见：其余事件面与记忆沉淀均不含（红线）。"""
    memory = _RecordingMemory()
    loop = DefaultLoop(
        planner=_ThinkingPlanner([Thinking("内部草稿")], Action(args={"reply": "结论"})),
        memory=memory,  # type: ignore[arg-type]
    )
    events = _collect_events(loop, "任务")
    assert [e.type for e in events if "内部草稿" in str(e.payload)] == ["loop.reasoning"]
    assert "内部草稿" not in "\n".join(entry.content for entry in memory.written)
    assert "结论" in "\n".join(entry.content for entry in memory.written)


# ---- 记忆维护节拍（spec：执行循环「维护节拍触发遗忘」） ----


class _ForgetSpy:
    """记录 forget 调用次数的记忆替身。"""

    def __init__(self, *, boom: bool = False) -> None:
        self.calls = 0
        self._boom = boom

    def read(self, query: str, budget: int = 0) -> list[MemoryEntry]:
        return []

    def write(self, layer: str, entry: MemoryEntry) -> str:
        return entry.id

    def forget(self, *, threshold: float = 0.0) -> list[str]:
        self.calls += 1
        if self._boom:
            raise RuntimeError("存储后端异常")
        return []


def _run_once(loop: DefaultLoop) -> None:
    loop.run("任务")


def test_maintenance_cadence_skips_before_interval() -> None:
    """未达维护间隔 → 收尾不触发遗忘（时钟与间隔注入）。"""
    now = [0.0]
    spy = _ForgetSpy()
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        memory=spy,  # type: ignore[arg-type]
        clock=lambda: now[0],
        maintenance_interval=60.0,
    )
    _run_once(loop)
    now[0] = 59.0
    _run_once(loop)
    assert spy.calls == 0


def test_maintenance_cadence_forgets_after_interval() -> None:
    """达维护间隔 → 收尾触发一次遗忘；再未到下一间隔不重复。"""
    now = [0.0]
    spy = _ForgetSpy()
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        memory=spy,  # type: ignore[arg-type]
        clock=lambda: now[0],
        maintenance_interval=60.0,
    )
    now[0] = 60.0
    _run_once(loop)
    assert spy.calls == 1
    now[0] = 100.0
    _run_once(loop)
    assert spy.calls == 1
    now[0] = 120.0
    _run_once(loop)
    assert spy.calls == 2  # noqa: PLR2004 — 第二次达间隔再触发一次


def test_maintenance_cadence_disabled_and_failure_degrades() -> None:
    """间隔 <=0 关闭节拍；维护失败降级不中断本轮（不抛给调用方）。"""
    now = [0.0]
    off = _ForgetSpy()
    DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        memory=off,  # type: ignore[arg-type]
        clock=lambda: now[0],
        maintenance_interval=0.0,
    ).run("任务")
    assert off.calls == 0

    now[0] = 0.0
    boom = _ForgetSpy(boom=True)
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        memory=boom,  # type: ignore[arg-type]
        clock=lambda: now[0],
        maintenance_interval=1.0,
    )
    now[0] = 10.0
    result = loop.run("任务")  # 不抛
    assert result.reply == "done"
    assert boom.calls == 1


def test_cold_path_cadence_calls_injected_callback() -> None:
    """达维护间隔 → 冷路径回调被调用一次（含未注入记忆时）；未达间隔不调用。"""
    now = [0.0]
    calls: list[str] = []
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        cold_path=lambda: calls.append("tick"),
        clock=lambda: now[0],
        maintenance_interval=60.0,
    )
    _run_once(loop)
    assert calls == []
    now[0] = 60.0
    _run_once(loop)
    assert calls == ["tick"]
    now[0] = 100.0
    _run_once(loop)
    assert calls == ["tick"]


def test_cold_path_failure_degrades() -> None:
    """冷路径回调抛错 → 降级留痕，本轮正常收尾（不抛给调用方）。"""

    def _boom() -> None:
        raise RuntimeError("冷路径异常")

    now = [0.0]
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        cold_path=_boom,
        clock=lambda: now[0],
        maintenance_interval=1.0,
    )
    now[0] = 10.0
    assert loop.run("任务").reply == "done"


# ---- trace 完成回调 + 模块归因（change 0101） ----


def test_trace_observer_called_once_per_run_with_trace_id() -> None:
    """收尾按轮调用 trace 完成回调一次，并交回本轮 trace_id。"""
    seen: list[str] = []
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        trace_observer=seen.append,
    )

    result = loop.run("任务")

    assert seen == [result.trace_id], "回调收到本轮 trace_id"


def test_trace_observer_sees_all_events_of_the_run() -> None:
    """回调触发时本轮遥测已齐（可完整回放，含 loop_finished）。"""
    tracer = Tracer()
    snapshots: list[list[str]] = []

    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        tracer=tracer,
        trace_observer=lambda trace_id: snapshots.append([e.kind for e in tracer.replay(trace_id)]),
    )

    loop.run("任务")

    assert snapshots, "回调被调用"
    assert "loop_finished" in snapshots[0], "回调时 loop_finished 已记录"


def test_trace_observer_not_throttled_by_maintenance_cadence() -> None:
    """trace 完成回调按轮，不受 maintenance_interval 节流。"""
    now = [0.0]
    calls: list[str] = []
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        trace_observer=calls.append,
        clock=lambda: now[0],
        maintenance_interval=3600.0,
    )

    _run_once(loop)
    _run_once(loop)  # 未达维护间隔

    assert len(calls) == 2, "未达维护间隔仍每轮回调"  # noqa: PLR2004


def test_trace_observer_failure_degrades() -> None:
    """回调抛错 → 降级留痕，本轮正常收尾（不抛给调用方）。"""
    tracer = _RecordingTracer()

    def _boom(trace_id: str) -> None:
        raise RuntimeError("登记失败")  # noqa: TRY003

    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        tracer=tracer,
        trace_observer=_boom,
    )

    result = loop.run("任务")

    assert result.reply == "done", "回调抛错不影响本轮结果"
    assert "trace_observer_failed" in tracer.kinds, "回调抛错降级留痕"


def test_trace_observer_absent_is_noop() -> None:
    tracer = _RecordingTracer()
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "done"}), tracer=tracer)

    assert loop.run("任务").reply == "done"
    assert "trace_observer_failed" not in tracer.kinds


def test_loop_failure_marks_module_attribution() -> None:
    """循环自身失败 ⇒ loop_finished 事件带 module_id="loop.default"（经落盘真路径断言）。"""
    exporter = _CapturingExporter()
    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.echo", args={"text": "x"}),
        tracer=Tracer(exporter=exporter),
        max_rounds=1,
    )

    result = loop.run("任务")

    assert result.failed, "轮数超限 → 本轮失败"
    finished = [e for e in exporter.events if e.kind == "loop_finished"]
    assert finished and finished[-1].module_id == "loop.default"


def test_loop_success_has_no_module_attribution() -> None:
    """正常收尾不产虚假缺陷证据（module_id 缺省为空）。"""
    exporter = _CapturingExporter()
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        tracer=Tracer(exporter=exporter),
    )

    loop.run("任务")

    finished = [e for e in exporter.events if e.kind == "loop_finished"]
    assert finished and finished[-1].module_id is None


# ---- trace 生命周期闭环（change 0103） ----


def test_loop_releases_trace_after_run() -> None:
    """收尾封口 ⇒ 本轮 trace 不再驻留内存（在途回放为空）。"""
    tracer = Tracer()
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "done"}), tracer=tracer)

    result = loop.run("任务")

    assert tracer.replay(result.trace_id) == [], "封口即释放"


def test_loop_emits_to_exporter_on_seal() -> None:
    """收尾封口把本轮事件交付导出器（落盘真路径打通）。"""
    exporter = _CapturingExporter()
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        tracer=Tracer(exporter=exporter),
    )

    loop.run("任务")

    kinds = [e.kind for e in exporter.events]
    assert "loop_finished" in kinds, "本轮事件经导出器产出"


def test_loop_seals_after_trace_observer_snapshot() -> None:
    """顺序约束：回调取快照时事件尚可回放，封口在回调之后。"""
    tracer = Tracer()
    snapshots: list[list[str]] = []
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        tracer=tracer,
        trace_observer=lambda trace_id: snapshots.append([e.kind for e in tracer.replay(trace_id)]),
    )

    result = loop.run("任务")

    assert snapshots and "loop_finished" in snapshots[0], "回调时本轮事件完整可回放"
    assert tracer.replay(result.trace_id) == [], "回调之后才封口释放"


def test_loop_does_not_accumulate_events_across_runs() -> None:
    """多轮执行后 Tracer 内存不随轮次增长（泄漏修复）。"""
    tracer = Tracer()
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "done"}), tracer=tracer)

    for _ in range(12):
        loop.run("任务")

    assert tracer._events == {}, "已封口 trace 不驻留"  # noqa: SLF001 — 内存有界断言


# ---- 流式中断留痕（change 0256） ----


class _HangingPlanner:
    """先外发一段增量，然后永不结束（模拟流式调用挂起）。"""

    async def astream(self, ctx):  # noqa: ANN001, ANN201 — 测试替身
        yield "a"
        await asyncio.Event().wait()


class _BoomPlanner:
    """外发一段增量后抛未收尾异常。"""

    async def astream(self, ctx):  # noqa: ANN001, ANN201 — 测试替身
        yield "a"
        raise RuntimeError("planner boom")  # noqa: TRY003 — 测试用哨兵异常


def test_interrupted_stream_records_loop_aborted_and_flushes() -> None:
    """消费方提前关闭 ⇒ 留痕 loop_aborted 并封口落盘（change 0256）。"""
    exporter = _CapturingExporter()
    tracer = Tracer(exporter=exporter)
    loop = DefaultLoop(planner=_HangingPlanner(), tracer=tracer)

    async def _run() -> str:
        trace_id = ""
        stream = loop.astream("任务")
        async for event in stream:
            if event.type == "loop_started":
                trace_id = event.payload["trace_id"]
            elif event.type == "reply_delta":
                await stream.aclose()
                break
        return trace_id

    trace_id = asyncio.run(_run())

    kinds = [event.kind for event in exporter.events]
    assert "loop_aborted" in kinds, "中断轮必须有可落盘的留痕"
    assert tracer.replay(trace_id) == [], "留痕后封口释放"


def test_raising_stream_records_loop_aborted_and_flushes() -> None:
    """执行体未收尾异常 ⇒ 先留痕封口，再原样抛出（change 0256）。"""
    exporter = _CapturingExporter()
    tracer = Tracer(exporter=exporter)
    loop = DefaultLoop(planner=_BoomPlanner(), tracer=tracer)

    with pytest.raises(RuntimeError, match="planner boom"):
        loop.run("任务")

    kinds = [event.kind for event in exporter.events]
    assert "loop_aborted" in kinds


def test_normal_stream_has_no_abort_event() -> None:
    """正常收尾不产 loop_aborted（既有事件面不变，change 0256）。"""
    exporter = _CapturingExporter()
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "ok"}),
        tracer=Tracer(exporter=exporter),
    )

    loop.run("任务")

    assert "loop_aborted" not in [event.kind for event in exporter.events]
