"""文档化记忆（notes）与 loop 的接线测试（change 0106）。

覆盖：任务前 Consult 注入 / 任务后 Update 写回 canonical / 钩子故障降级 /
摘要经 LLMPlanner 进 system prompt。loop 侧只认 Callable 钩子（架构红线：
loop 不 import notes），故此处用注入闭包 + 真 NoteStore 验证行为。
"""

from __future__ import annotations

import asyncio

from core.configuration import ConfigManager
from core.context import Compactor
from core.llm_provider import LLMResponse, TokenUsage
from core.loop import Action, DefaultLoop, LoopContext
from core.loop.planner import LLMPlanner
from core.memory import MemoryEntry, MemoryStore
from core.notes import NoteEntry, NoteStore
from core.observability import TraceEvent
from core.runtime import build_runtime
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


class _RecordingTracer:
    """收集事件 kind（判定降级留痕）；满足 loop 侧生命周期面（start/end/record）。"""

    def __init__(self) -> None:
        self.kinds: list[str] = []

    def start_trace(self, _task_id: str) -> str:
        return "trace-stub"

    def end_trace(self, _trace_id: str) -> None:
        return None

    def record(self, event: TraceEvent) -> None:
        self.kinds.append(event.kind)


class _FakeLLM:
    """记录 LLMRequest、返回固定 content 的假 LLM（不出网）。"""

    def __init__(self, content: str) -> None:
        self._content = content
        self.requests: list[object] = []

    async def acompletion(self, request: object) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            content=self._content,
            usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
            finish_reason="stop",
            provider="fake",
            model="test-model",
        )


def _store(tmp_path) -> NoteStore:
    return NoteStore(path=tmp_path)


def _write_tool() -> Tool:
    """写效应工具（change 0176 效应闸门：只有写效应轮才写回笔记）。

    效应闸门按**工具名**判定，故此替身只需 id 落在写效应集内；`coeffects=[]` 以免离线
    运行因缺 `CoeffectResolver` 而 `COEFFECT_MISSING`（闸门会据此视为失败、不写回）。
    """
    return Tool(
        definition=ToolDef(
            tool_id="tools.file_write",
            description="write",
            schema={"type": "object", "properties": {"text": {"type": "string"}}},
            coeffects=[],
            reversible=True,
        ),
        handler=lambda text: f"written:{text}",
    )


def _tool_then_reply(*, reply: str, tool_id: str = "tools.echo"):
    """首轮调工具、次轮终止回复的 planner（保证 steps 非空）。"""

    def planner(ctx: LoopContext) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id=tool_id, args={"text": "中间结论"})
        return Action(args={"reply": reply})

    return planner


# ---- 任务前 Consult ----


def test_loop_consult_hook_sees_task_and_feeds_context(tmp_path) -> None:
    store = _store(tmp_path)
    store.update(NoteEntry(note_id="部署", title="部署流程", content="先备份再滚动更新"))
    seen: list[str] = []
    captured: list[str] = []

    def consult(task: str) -> str:
        seen.append(task)
        return store.digest(task)

    def planner(ctx: LoopContext) -> Action:
        captured.append(ctx.notes)
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, notes_consult=consult)
    loop.run("部署流程怎么走")

    assert seen == ["部署流程怎么走"], "任务文本交给 Consult 钩子"
    assert captured and "先备份再滚动更新" in captured[0], "摘要先于推理注入 ctx.notes"


def test_loop_without_consult_hook_leaves_notes_empty() -> None:
    captured: list[str] = []
    loop = DefaultLoop(
        planner=lambda ctx: captured.append(ctx.notes) or Action(args={"reply": "done"})
    )
    loop.run("任意任务")

    assert captured == [""], "缺省未注入 ⇒ 空摘要（不注入笔记块）"


def test_loop_consult_failure_degrades_and_does_not_change_outcome() -> None:
    tracer = _RecordingTracer()

    def boom(task: str) -> str:
        raise RuntimeError("笔记库不可用")  # noqa: TRY003

    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}), tracer=tracer, notes_consult=boom
    )
    result = loop.run("任务")

    assert not result.failed and result.reply == "done", "Consult 抛错不影响本轮结果"
    assert "notes_consult_failed" in tracer.kinds, "降级留痕"


# ---- 归档来源排除面：提升产物不进 Consult 命中节选（change 0180 / ADR-0171 / 账本 E117） ----


def _promoted_note(*, pinned: bool = False) -> NoteEntry:
    """提升产物：`source="notes.promote"`、正文即会话摘要（词法可命中）。"""
    return NoteEntry(
        note_id="session-s1",
        title="会话摘要 s1",
        content="部署流程：先备份再滚动更新",
        tags=["promotion", "summary"],
        source="notes.promote",
        search_queries=["部署流程"],
        pinned=pinned,
    )


def test_loop_notes_block_excludes_promoted_summary(tmp_path) -> None:
    """端到端：提升产物的正文不进「相关笔记」块，普通命中照常。"""
    store = _store(tmp_path)
    store.update(_promoted_note())
    store.update(NoteEntry(note_id="deploy", title="部署流程手册", content="先备份再滚动更新"))
    captured: list[tuple[str, str]] = []

    loop = DefaultLoop(
        planner=lambda ctx: (
            captured.append((ctx.notes, ctx.pinned_notes)) or Action(args={"reply": "done"})
        ),
        notes_consult=store.digest,
        pinned_notes_consult=store.pinned_digest,
    )
    loop.run("部署流程怎么走")

    notes, pinned = captured[0]
    assert "先备份再滚动更新" in notes, "普通笔记命中照常注入"
    assert "session-s1" in notes, "提升产物仍以清单标题在场"
    assert "会话摘要 s1（session-s1）" not in notes, "提升产物不进命中节选（免与长期摘要块重复）"
    assert pinned == "", "半自动提升不占常驻预算"


def test_loop_promoted_note_pinned_stays_in_single_channel(tmp_path) -> None:
    """置常驻的提升产物只经「常驻笔记」块在场：命中面不再重复同一篇。"""
    store = _store(tmp_path)
    store.update(_promoted_note(pinned=True))
    captured: list[tuple[str, str]] = []

    loop = DefaultLoop(
        planner=lambda ctx: (
            captured.append((ctx.notes, ctx.pinned_notes)) or Action(args={"reply": "done"})
        ),
        notes_consult=store.digest,
        pinned_notes_consult=store.pinned_digest,
    )
    loop.run("部署流程怎么走")

    notes, pinned = captured[0]
    assert "先备份再滚动更新" not in notes, "常驻版提升产物不进命中节选"
    assert "先备份再滚动更新" in pinned, "正文经常驻通道完整在场（通道分列）"


# ---- 任务后 Update ----


def test_loop_turn_observer_writes_canonical_note(tmp_path) -> None:
    store = _store(tmp_path)
    provider = ToolProvider()
    provider.register(_write_tool())

    loop = DefaultLoop(
        planner=_tool_then_reply(reply="done", tool_id="tools.file_write"),
        tools=provider,
        max_rounds=3,
        turn_observer=lambda task, steps, ok: store.observe_turn(task, steps, ok=ok),
    )
    loop.run("修复 登录 超时")

    note_id = store.list()[0].note_id
    raw = (tmp_path / f"{note_id}.md").read_text(encoding="utf-8")
    assert "## 解决过程" in raw, "成功轮写回 canonical Markdown"
    # change 0171：正文为人类可读行（工具名 + 参数摘要 + 结果节选），**不落** ReAct 消息原文。
    assert "tools.file_write" in raw and "中间结论" in raw, "写回内容承载可读的行动/结果序列"
    assert '{"tool_id"' not in raw and '{"data"' not in raw, "不落 JSON 原文转储"


def test_loop_pure_read_turn_does_not_write_note(tmp_path) -> None:
    """纯读轮（无写效应动作）⇒ 效应闸门跳过写回（change 0176 / ADR-0167）。"""
    store = _store(tmp_path)
    provider = ToolProvider()
    provider.register(_echo_tool())

    loop = DefaultLoop(
        planner=_tool_then_reply(reply="done"),
        tools=provider,
        max_rounds=3,
        turn_observer=lambda task, steps, ok: store.observe_turn(task, steps, ok=ok),
    )
    loop.run("查一下资料")

    assert list(tmp_path.glob("*.md")) == [], "仅调过只读工具的轮次不得写回笔记"


def test_loop_reply_only_turn_does_not_write_note(tmp_path) -> None:
    """纯文字回复轮（无工具动作）⇒ 有意义闸门跳过写回（change 0171）。"""
    store = _store(tmp_path)
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "你好呀"}),
        turn_observer=lambda task, steps, ok: store.observe_turn(task, steps, ok=ok),
    )
    loop.run("你好")

    assert list(tmp_path.glob("*.md")) == [], "无行动轮次不创建笔记"


def test_loop_failed_round_does_not_write_note(tmp_path) -> None:
    store = _store(tmp_path)
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "unused"}),
        max_rounds=0,
        turn_observer=lambda task, steps, ok: store.observe_turn(task, steps, ok=ok),
    )
    result = loop.run("超限任务")

    assert result.failed, "轮数超限 ⇒ 本轮失败"
    assert list(tmp_path.glob("*.md")) == [], "失败轮不写回笔记"


# ---- Consult → Build → Update 全闭环（同一存储：读到的即写回的） ----


def test_consult_update_loop_roundtrip_through_loop(tmp_path) -> None:
    store = _store(tmp_path)
    provider = ToolProvider()
    provider.register(_write_tool())

    loop = DefaultLoop(
        planner=_tool_then_reply(reply="done", tool_id="tools.file_write"),
        tools=provider,
        max_rounds=3,
        notes_consult=store.digest,
        turn_observer=lambda task, steps, ok: store.observe_turn(task, steps, ok=ok),
    )
    loop.run("整理发布流程")

    # 第二轮 Consult 读到第一轮 Update 写回的笔记（闭环成立）
    digest = store.digest("整理发布流程")
    assert "整理发布流程" in digest


# ---- 摘要进 LLMPlanner 的 system prompt ----


def test_builtin_workflow_skill_registered_and_routable(monkeypatch, tmp_path) -> None:
    """组合根注册内置循环技能，且可经既有词法路由命中（spec「循环技能可被路由」）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n",
        encoding="utf-8",
    )
    runtime = build_runtime(ConfigManager(yaml_path=str(cfg)))

    skill = runtime.skill_router._library.lookup("skills.notes.consult_build_update")
    assert skill is not None, "组合根注册内置循环技能"
    assert "Consult" in skill.instructions and "Update" in skill.instructions, "两段纪律齐备"

    matched = [m.skill.skill_id for m in runtime.skill_router.match("notes 文档化记忆")]
    assert "skills.notes.consult_build_update" in matched, "经既有词法路由命中（不另开路由通道）"


def test_planner_injects_notes_block_only_when_present() -> None:
    llm = _FakeLLM("done")
    planner = LLMPlanner(llm, model="test-model")  # type: ignore[arg-type]

    with_notes = LoopContext(
        messages=[{"role": "user", "content": "任务"}],
        notes="命中笔记：先备份再滚动更新",
    )
    asyncio.run(planner(with_notes))
    prompt = llm.requests[0].messages[0].content  # type: ignore[attr-defined]
    assert "相关笔记：" in prompt
    assert "先备份再滚动更新" in prompt

    llm2 = _FakeLLM("done")
    planner2 = LLMPlanner(llm2, model="test-model")  # type: ignore[arg-type]
    asyncio.run(planner2(LoopContext(messages=[{"role": "user", "content": "任务"}])))
    assert "相关笔记：" not in llm2.requests[0].messages[0].content  # type: ignore[attr-defined]


# ---- 常驻（pinned）笔记：每轮无条件注入（change 0149 / ADR-0141 / 账本 E93） ----


def test_loop_pinned_hook_populates_context_without_task_arg(tmp_path) -> None:
    """常驻注入与 query 无关：零参钩子每轮无条件填 `ctx.pinned_notes`。"""
    store = _store(tmp_path)
    store.update(
        NoteEntry(note_id="constraints", title="硬约束", content="接口必须 HTTPS", pinned=True)
    )
    calls: list[int] = []

    def pinned() -> str:
        calls.append(1)
        return store.pinned_digest()

    captured: list[str] = []
    loop = DefaultLoop(
        planner=lambda ctx: captured.append(ctx.pinned_notes) or Action(args={"reply": "done"}),
        pinned_notes_consult=pinned,
    )
    loop.run("与约束完全无关的任务")

    assert calls == [1], "常驻钩子每轮调用恰一次"
    # 若 loop 误传任务文本，零参闭包会抛 TypeError 而降级为空 ⇒ 有内容即证「零参调用」
    assert captured and "接口必须 HTTPS" in captured[0], "常驻正文进上下文（不依赖 query 命中）"


def test_loop_without_pinned_hook_leaves_pinned_notes_empty() -> None:
    captured: list[str] = []
    loop = DefaultLoop(
        planner=lambda ctx: captured.append(ctx.pinned_notes) or Action(args={"reply": "done"})
    )
    loop.run("任意任务")

    assert captured == [""], "缺省未注入 ⇒ 空（不注入常驻块）"


def test_loop_pinned_consult_failure_degrades() -> None:
    tracer = _RecordingTracer()

    def boom() -> str:
        raise RuntimeError("常驻源不可用")  # noqa: TRY003

    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "done"}),
        tracer=tracer,
        pinned_notes_consult=boom,
    )
    result = loop.run("任务")

    assert not result.failed and result.reply == "done", "常驻注入抛错不影响本轮结果"
    assert "pinned_notes_consult_failed" in tracer.kinds, "降级留痕"


def test_planner_injects_pinned_block_before_related_notes() -> None:
    llm = _FakeLLM("done")
    planner = LLMPlanner(llm, model="test-model")  # type: ignore[arg-type]
    ctx = LoopContext(
        messages=[{"role": "user", "content": "任务"}],
        pinned_notes="接口必须 HTTPS",
        notes="命中笔记：先备份再滚动更新",
    )
    asyncio.run(planner(ctx))
    prompt = llm.requests[0].messages[0].content  # type: ignore[attr-defined]

    assert "常驻笔记" in prompt and "接口必须 HTTPS" in prompt
    assert "相关笔记：" in prompt
    assert prompt.index("常驻笔记") < prompt.index("相关笔记"), "常驻块先于「相关笔记」块（独立块）"


def test_planner_omits_pinned_block_when_empty() -> None:
    llm = _FakeLLM("done")
    planner = LLMPlanner(llm, model="test-model")  # type: ignore[arg-type]
    asyncio.run(planner(LoopContext(messages=[{"role": "user", "content": "任务"}])))

    assert "常驻笔记" not in llm.requests[0].messages[0].content  # type: ignore[attr-defined]


# ---- 设计裁决护栏：loop 压实不自动提升（change 0150 / ADR-0142 / 账本 E94；
#      0153 收窄为「仅首次越界半自动」/ ADR-0145 / 路线图 G3） ----


def test_loop_compaction_below_bound_does_not_promote(tmp_path) -> None:
    """跑一轮触发压实的 loop，其会话摘要**未越过**滚动上界 ⇒ 半自动提升不触发。

    半自动提升**仅**由「摘要**首次越过**滚动上界」触发（change 0153 / ADR-0145），
    **不**由「跑了一轮压实」触发 —— 摘要未越界时甚至**不交付**注入的提升钩子。
    """
    delivered: list[tuple[str, MemoryEntry]] = []
    memory = MemoryStore(
        summarizer=lambda entries: "会话结论：必须 HTTPS",
        summary_promoter=lambda sid, entry: delivered.append((sid, entry)),
    )
    memory.write(
        "L2",
        MemoryEntry(
            id="e0",
            layer="L2",
            content="事实零",
            tags=["loop"],
            source="loop",
            session_id="s1",
            kind="episodic",
            trace_id="t",
        ),
    )
    provider = ToolProvider()
    provider.register(_echo_tool())
    notes_dir = tmp_path / "notes"
    store = NoteStore(path=notes_dir)
    loop = DefaultLoop(
        planner=_tool_then_reply(reply="done"),
        tools=provider,
        memory=memory,
        compactor=Compactor(memory=memory, round_threshold=0),
        max_rounds=3,
        notes_consult=store.digest,
        turn_observer=lambda task, steps, ok: store.observe_turn(task, steps, ok=ok),
    )

    loop.run("会话结论 任务", session_id="s1")

    assert memory.summary_for("s1") is not None, "压实确已产摘要（非空转）"
    assert delivered == [], "摘要未越界 ⇒ 不交付提升钩子"
    assert list(notes_dir.glob("session-*.md")) == [], "提升不被自动触发"
