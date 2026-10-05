"""文档化记忆（notes）与 loop 的接线测试（change 0106）。

覆盖：任务前 Consult 注入 / 任务后 Update 写回 canonical / 钩子故障降级 /
摘要经 LLMPlanner 进 system prompt。loop 侧只认 Callable 钩子（架构红线：
loop 不 import notes），故此处用注入闭包 + 真 NoteStore 验证行为。
"""

from __future__ import annotations

import asyncio

from core.configuration import ConfigManager
from core.llm_provider import LLMResponse, TokenUsage
from core.loop import Action, DefaultLoop, LoopContext
from core.loop.planner import LLMPlanner
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


def _tool_then_reply(*, reply: str):
    """首轮调工具、次轮终止回复的 planner（保证 steps 非空）。"""

    def planner(ctx: LoopContext) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "中间结论"})
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


# ---- 任务后 Update ----


def test_loop_turn_observer_writes_canonical_note(tmp_path) -> None:
    store = _store(tmp_path)
    provider = ToolProvider()
    provider.register(_echo_tool())

    loop = DefaultLoop(
        planner=_tool_then_reply(reply="done"),
        tools=provider,
        max_rounds=3,
        turn_observer=lambda task, steps, ok: store.observe_turn(task, steps, ok=ok),
    )
    loop.run("修复 登录 超时")

    note_id = store.list()[0].note_id
    raw = (tmp_path / f"{note_id}.md").read_text(encoding="utf-8")
    assert "## 解决过程" in raw, "成功轮写回 canonical Markdown"
    assert "tool" in raw, "写回内容承载行动/结果序列"


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
    provider.register(_echo_tool())

    loop = DefaultLoop(
        planner=_tool_then_reply(reply="done"),
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
