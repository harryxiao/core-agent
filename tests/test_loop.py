"""loop 单元测试（对齐 §14 契约 + M2 验收锚点）。

覆盖：停止条件退出 / 单轮失败回滚 / 中间件被拒短路 / 循环与 token 超限 /
同步异步等价 / 端到端冒烟（loop 驱动 tool-use + memory）。
"""

from __future__ import annotations

import asyncio
import time

from core.context import Compactor
from core.loop import Action, DefaultLoop
from core.memory import MemoryEntry, MemoryStore
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
    loop = _compacting_loop(memory, Compactor(memory=memory, round_threshold=1))

    loop.run("hi")

    entries = {e.id: e for e in memory.audit()}
    summary = entries.get("compaction.summary.s1")
    assert summary is not None, "轮数达阈值 → 触发压实，历史 episodic 提炼为 semantic 摘要"
    assert summary.kind == "semantic" and "from:loop.prior" in summary.tags
    assert "compaction.fact.0" in entries, "上下文压实产物同批落 L2（persist）"
    assert entries["compaction.fact.0"].kind == "semantic"
    assert dict(memory.index().entries)["loop.prior"] == "L4", "被摘要的原条目归档 L4"


def test_loop_compaction_triggers_on_token_budget_and_still_terminates() -> None:
    memory = _summary_memory()
    memory.write("L2", _prior_entry())
    loop = _compacting_loop(memory, Compactor(memory=memory, round_threshold=100), token_budget=1)

    result = loop.run("hi")

    assert "TOKEN_BUDGET_EXCEEDED" in result.reply, "压实不改终止语义"
    assert "compaction.summary.s1" in {e.id for e in memory.audit() if e.kind == "semantic"}


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
    loop = _compacting_loop(memory, Compactor(memory=memory, round_threshold=100), token_budget=0)

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
    loop = _compacting_loop(memory, Compactor(memory=memory, round_threshold=1))

    loop.run("hi")

    layers = dict(memory.index().entries)
    assert layers["loop.prior"] == "L4", "压实触发 → 顺带遗忘陈旧低分条目"
    assert layers["loop.warm"] == "L2", "高复用条目不被遗忘"
    assert "loop.prior" in {e.id for e in memory.audit()}, "归档不删除，仍可审计"


# ---- SOP 收尾钩子（0043） ----


class _RecordingTracer:
    """记录事件 kind，验证降级留痕。"""

    def __init__(self) -> None:
        self.kinds: list[str] = []

    def record(self, event) -> None:  # noqa: ANN001
        self.kinds.append(event.kind)


def test_loop_fires_turn_observer_on_success() -> None:
    seen: list[tuple[str, list[str], bool]] = []
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
        turn_observer=lambda task, steps, ok: seen.append((task, steps, ok)),
    )

    loop.run("整理会议纪要")

    assert len(seen) == 1, "成功收尾触发一次"
    task, steps, ok = seen[0]
    assert ok is True, "成功轮 ok=True"
    assert task == "整理会议纪要", "钩子拿到任务文本"
    assert any("tools.echo" in step for step in steps), "行动/结果序列承载工具调用"


def test_loop_fires_turn_observer_on_failure() -> None:
    seen: list[tuple[str, list[str], bool]] = []
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "unused"}),
        max_rounds=0,
        turn_observer=lambda task, steps, ok: seen.append((task, steps, ok)),
    )

    result = loop.run("超限任务")

    assert result.failed, "轮数超限 → 本轮失败"
    assert len(seen) == 1 and seen[0][2] is False, "失败轮也提交（ok=False，供反馈判定）"


def test_loop_turn_observer_error_does_not_break_round() -> None:
    tracer = _RecordingTracer()

    def boom(task: str, steps: list[str], ok: bool) -> None:
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
