"""ui 单元测试（对齐契约红线：三模复用 / SSE 流式 / 四错误码 / LLM key 只存引用）。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest

from core.beast import BeastActivator
from core.configuration.models import LLMConfig
from core.loop import LoopEvent
from core.memory import MemoryEntry
from core.permission import ApprovalChannel
from core.pet.core import PetControl, PetManager, PetSession, PetTask, PetTaskKind
from core.ui import (
    CLIBridge,
    DesktopBridge,
    Event,
    SessionRegistry,
    UIAPILayer,
    UiError,
    UiErrorCode,
    WebBridge,
)


class FakeLoop:
    """产出受控 LoopEvent 流的 loop 替身。"""

    def __init__(self, events: list[LoopEvent]) -> None:
        self._events = events

    async def astream(self, user_input: str, *, session_id: str = ""):
        for event in self._events:
            yield event


def _llm(key: str = "${OPENAI_API_KEY}") -> LLMConfig:
    return LLMConfig(provider="openai", model="gpt-4o", endpoint="https://x", api_key_ref=key)


def _collect(api: UIAPILayer, session_id: str, user_input: str, **kwargs) -> list[Event]:
    async def _run() -> list[Event]:
        return [event async for event in api.run_loop(session_id, user_input, **kwargs)]

    return asyncio.run(_run())


def _streaming_api() -> tuple[UIAPILayer, str]:
    api = UIAPILayer(
        loop=FakeLoop(
            [
                LoopEvent("loop_started", {"trace_id": "t1"}),
                LoopEvent("step_completed", {"round": 1, "failed": False}),
                LoopEvent("loop_finished", {"reply": "done"}),
            ]
        )
    )
    api.set_llm_config(_llm())
    return api, api.create_session("cli")


# ---- 三模复用同一内核 ----


def test_three_modes_share_api_layer() -> None:
    api = UIAPILayer()
    connected: list[UIAPILayer] = []
    CLIBridge(api=api, connect_impl=lambda a, _s: connected.append(a)).connect()
    assert connected == [api]
    resumed: list[tuple[UIAPILayer, str]] = []
    CLIBridge(
        api=api, connect_impl=lambda a, s: resumed.append((a, s)), session_id="sid-1"
    ).connect()
    assert resumed == [(api, "sid-1")]
    calls: list[tuple] = []
    WebBridge(api=api, serve_impl=lambda a, h, p: calls.append((a, h, p))).serve("0.0.0.0", 8000)
    assert calls == [(api, "0.0.0.0", 8000)]
    started: list[UIAPILayer] = []
    DesktopBridge(api=api, start_impl=started.append).start_sidecar()
    assert started == [api]


# ---- SSE 流式事件 ----


def test_run_loop_streams_sse_events() -> None:
    api, session_id = _streaming_api()
    streamed = _collect(api, session_id, "hi")
    assert [e.type for e in streamed] == ["session.created", "loop.action", "loop.result"]
    assert streamed[0].payload["session_id"] == session_id
    assert streamed[0].payload["trace_id"] == "t1"


def test_reply_delta_maps_to_dedicated_type() -> None:
    """流式增量以**专类型** `loop.delta` 推送（change `0132` / ADR-0125 / 账本 E65）。

    增量与终态不再共型：增量帧类型 = `loop.delta`（载荷恒为 `{"text": …}`），终态帧类型 =
    `loop.result`（载荷 `LoopResult`）。此前二者共用 `loop.result` ⇒ Web 前端按「无 reply
    即序列化 JSON」处理，每帧渲染一段 JSON。
    """
    from core.loop import LoopResult  # noqa: PLC0415 — 流式事件构造

    api = UIAPILayer(
        loop=FakeLoop(
            [
                LoopEvent("loop_started", {"trace_id": "t1"}),
                LoopEvent("reply_delta", {"text": "你"}),
                LoopEvent("reply_delta", {"text": "好"}),
                LoopEvent("loop_finished", LoopResult(reply="你好", trace_id="t1")),
            ]
        )
    )
    api.set_llm_config(_llm())
    session_id = api.create_session("cli")

    streamed = _collect(api, session_id, "hi")

    assert [e.type for e in streamed] == [
        "session.created",
        "loop.delta",
        "loop.delta",
        "loop.result",
    ]
    assert [e.payload for e in streamed[1:3]] == [{"text": "你"}, {"text": "好"}]
    assert not isinstance(streamed[3].payload, dict), "终态载荷为 LoopResult 对象"


def test_loop_reasoning_maps_to_identity_type() -> None:
    """思考回显事件以 **identity** 类型透传（change 0145 / ADR-0137 / 账本 E59）。

    `loop.reasoning` 与 `loop.delta` 载荷同形（`{"text": …}`）而**类型相异**：前者为未定稿
    推理原文、后者为回复增量，三端按专类型分别落折叠块与正文。类型须在 `_EVENT_MAP`
    **显式**登记（该表是本层「LoopEvent → SSE 类型」的唯一契约面；缺登记虽可经 `_map_event`
    的 identity 兜底侥幸透传，但契约面即失真）。
    """
    from core.loop import LoopResult  # noqa: PLC0415 — 流式事件构造
    from core.ui.api import _EVENT_MAP  # noqa: PLC0415, PLC2701 — 契约表断言锚点

    assert _EVENT_MAP["loop.reasoning"] == "loop.reasoning"

    api = UIAPILayer(
        loop=FakeLoop(
            [
                LoopEvent("loop_started", {"trace_id": "t1"}),
                LoopEvent("loop.reasoning", {"text": "想"}),
                LoopEvent("reply_delta", {"text": "好"}),
                LoopEvent("loop_finished", LoopResult(reply="好", trace_id="t1")),
            ]
        )
    )
    api.set_llm_config(_llm())
    session_id = api.create_session("cli")

    streamed = _collect(api, session_id, "hi")

    assert [e.type for e in streamed] == [
        "session.created",
        "loop.reasoning",
        "loop.delta",
        "loop.result",
    ]
    assert streamed[1].payload == {"text": "想"}


def test_compaction_progress_events_are_explicitly_mapped() -> None:
    """压实进度事件显式登记到契约表（change 0256）。"""
    from core.ui.api import _EVENT_MAP  # noqa: PLC0415, PLC2701 — 契约表断言锚点

    assert _EVENT_MAP["loop.compacting"] == "loop.compacting"
    assert _EVENT_MAP["loop.compacted"] == "loop.compacted"


# ---- 四错误码 ----


def test_run_loop_unknown_session() -> None:
    api, _ = _streaming_api()
    with pytest.raises(UiError) as exc_info:
        _collect(api, "nope", "hi")
    assert exc_info.value.code is UiErrorCode.UI_SESSION_NOT_FOUND


def test_run_loop_llm_key_unset() -> None:
    api = UIAPILayer(loop=FakeLoop([]))
    session_id = api.create_session("cli")
    with pytest.raises(UiError) as exc_info:
        _collect(api, session_id, "hi")
    assert exc_info.value.code is UiErrorCode.UI_LLM_KEY_UNSET


def test_run_loop_modality_missing() -> None:
    api, session_id = _streaming_api()
    with pytest.raises(UiError) as exc_info:
        _collect(api, session_id, "hi", modalities=["image"])
    assert exc_info.value.code is UiErrorCode.UI_MODALITY_MISSING


def test_run_loop_maps_action_events() -> None:
    """工具动作事件（spec：异步流式执行）：action_* → loop.action_* 前缀透传。"""
    api = UIAPILayer(
        loop=FakeLoop(
            [
                LoopEvent("loop_started", {"trace_id": "t1"}),
                LoopEvent(
                    "action_started", {"round": 0, "tool_id": "tools.echo", "args": {"text": "hi"}}
                ),
                LoopEvent(
                    "action_completed",
                    {
                        "round": 0,
                        "tool_id": "tools.echo",
                        "ok": True,
                        "duration_ms": 12,
                        "output": "echo:hi",
                    },
                ),
                LoopEvent("step_completed", {"round": 1, "failed": False}),
                LoopEvent("loop_finished", {"reply": "done"}),
            ]
        )
    )
    api.set_llm_config(_llm())
    session_id = api.create_session("cli")

    streamed = _collect(api, session_id, "hi")

    assert [e.type for e in streamed] == [
        "session.created",
        "loop.action_started",
        "loop.action_completed",
        "loop.action",
        "loop.result",
    ]
    assert streamed[1].payload["tool_id"] == "tools.echo"
    assert streamed[2].payload["ok"] is True


def test_barge_in() -> None:
    with pytest.raises(UiError) as exc_info:
        UIAPILayer().barge_in()
    assert exc_info.value.code is UiErrorCode.UI_BARGEIN


# ---- LLM key 只存引用 ----


def test_get_llm_config_returns_reference() -> None:
    api = UIAPILayer()
    api.set_llm_config(_llm("${OPENAI_API_KEY}"))
    assert api.get_llm_config().api_key_ref == "${OPENAI_API_KEY}"


def test_set_llm_config_rejects_plaintext() -> None:
    with pytest.raises(UiError) as exc_info:
        UIAPILayer().set_llm_config(_llm("sk-secret-plaintext"))
    assert exc_info.value.code is UiErrorCode.UI_LLM_KEY_UNSET


def test_apply_llm_config_rejects_plaintext() -> None:
    with pytest.raises(UiError) as exc_info:
        UIAPILayer().apply_llm_config(_llm("sk-secret-plaintext"))
    assert exc_info.value.code is UiErrorCode.UI_LLM_KEY_UNSET


def test_apply_llm_config_skips_loop_without_limits_protocol() -> None:
    """loop 不支持 `LimitsConfigurable` ⇒ 静默跳过：换策略插件不该让保存配置失败（change 0099）。"""
    api = UIAPILayer(loop=FakeLoop([]))
    api.apply_llm_config(_llm(), output_reserve=4096, max_rounds=3)  # 不抛
    assert api.get_llm_config().model == "gpt-4o"
    assert api.get_loop_limits() is None  # 无配置源 ⇒ 不假装有生效值


# ---- TUI（ReplApp headless 冒烟）----


def _tui_app() -> object:
    pytest.importorskip("textual")
    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    api, _ = _streaming_api()
    return build_app(api)


def _timeline_text(app: object) -> str:
    """时间线全量文本：Static 取渲染文本，Collapsible 取标题 + 内部 Static，
    Markdown 取回原文（app._last_reply，Markdown 无公开源文本取口）。"""
    from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
    from textual.widgets import Collapsible, Markdown, Static  # noqa: PLC0415 — 可选依赖懒 import

    parts: list[str] = []
    for child in app.query_one("#timeline", Vertical).children:
        if isinstance(child, Collapsible):
            parts.append(str(child.title))
            parts.extend(str(s.render()) for s in child.query(Static))
        elif isinstance(child, Markdown):
            parts.append(str(getattr(app, "_last_reply", "")))
        else:
            parts.append(str(child.render()))
    return "".join(parts)


def test_tui_empty_enter_does_not_exit() -> None:
    """空回车忽略不退出（IME 确认误触防护）；退出走 Ctrl+Q/Ctrl+C。"""
    app = _tui_app()

    async def _drive() -> bool:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            app.query_one("#input", Input).focus()
            await pilot.press("enter")  # 空输入直接回车
            await pilot.pause()
            running = app.is_running
        return running

    assert asyncio.run(_drive()) is True


def test_tui_message_roundtrip_stops_spinner() -> None:
    """回车提交后输入清空、工作状态行（✻ spinner）回合收尾隐藏。"""
    app = _tui_app()

    async def _drive() -> tuple[bool, bool]:
        from textual.widgets import Input, Static  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            inp.value = "hi"
            await pilot.press("enter")
            await pilot.pause()
            running = app.is_running
            spinner_hidden = app.query_one("#spinner", Static).display is False
            input_cleared = inp.value == ""
        return running and input_cleared, spinner_hidden

    ok, spinner_hidden = asyncio.run(_drive())
    assert ok is True
    assert spinner_hidden is True


def test_tui_streams_deltas_then_flushes_once() -> None:
    """流式 reply_delta：增量直接落时间线尾部同一滚动流，终态原位换 Markdown 一次。"""
    from core.loop import LoopResult  # noqa: PLC0415 — 流式事件构造

    api = UIAPILayer(
        loop=FakeLoop(
            [
                LoopEvent("loop_started", {"trace_id": "t1"}),
                LoopEvent("reply_delta", {"text": "你"}),
                LoopEvent("reply_delta", {"text": "好"}),
                LoopEvent("loop_finished", LoopResult(reply="你好", trace_id="t1")),
            ]
        )
    )
    api.set_llm_config(_llm())
    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    app = build_app(api)

    async def _drive() -> tuple[bool, int, str]:
        from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
        from textual.widgets import Input, Markdown  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            inp.value = "hi"
            await pilot.press("enter")
            await pilot.pause()
            timeline = app.query_one("#timeline", Vertical)
            md_count = len(timeline.query(Markdown))
            stream_reset = app._tail_widget is None
            reply = str(app._last_reply)
            running = app.is_running
        return running and stream_reset, md_count, reply

    ok, md_count, reply = asyncio.run(_drive())
    assert ok is True
    assert md_count == 1  # 终态全文只渲染一次（流式行原位替换，不重复）
    assert reply == "你好"


def test_tui_large_code_fence_not_split() -> None:
    """大代码块（超 _TAIL_SPLIT、未超硬上限）流式期间不按行固化，整块不拆断。"""
    from core.loop import LoopResult  # noqa: PLC0415 — 流式事件构造
    from core.ui.repl import _TAIL_FENCE_CAP, _TAIL_SPLIT, build_app  # noqa: PLC0415

    body = "\n".join(f"print({i})" for i in range(400))
    payload = f"```python\n{body}\n```\n"
    assert _TAIL_SPLIT < len(payload) < _TAIL_FENCE_CAP
    events = [LoopEvent("loop_started", {"trace_id": "t1"})]
    events += [
        LoopEvent("reply_delta", {"text": chunk}) for chunk in payload.splitlines(keepends=True)
    ]
    events.append(LoopEvent("loop_finished", LoopResult(reply=payload, trace_id="t1")))
    api = UIAPILayer(loop=FakeLoop(events))
    api.set_llm_config(_llm())
    app = build_app(api)

    async def _drive() -> tuple[int, str]:
        from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
        from textual.widgets import Input, Markdown  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            inp.value = "hi"
            await pilot.press("enter")
            await pilot.pause()
            md_count = len(app.query_one("#timeline", Vertical).query(Markdown))
            return md_count, str(app._last_reply)

    md_count, reply = asyncio.run(_drive())
    assert md_count == 1  # 大围栏整块一块，未被拆成多段
    assert reply == payload


def test_tui_approval_prompt_y_n() -> None:
    """高风险审批：TUI 弹 y/n 提示；非法输入重输提示不决断，y 批准。"""
    channel = ApprovalChannel()
    api = UIAPILayer(loop=FakeLoop([]), approval=channel)
    api.set_llm_config(_llm())
    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    app = build_app(api)

    async def _drive() -> tuple[bool, bool, bool]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            task = asyncio.ensure_future(
                channel.ask("tools.web_fetch", {"url": "https://x"}, "出站网络抓取")
            )
            await pilot.pause()
            prompt_seen = "需审批" in _timeline_text(app)
            inp.value = "x"  # 非法输入：提示重输，审批保持挂起
            await pilot.press("enter")
            await pilot.pause()
            still_pending = app._approval_future is not None and not app._approval_future.done()
            inp.value = "y"
            await pilot.press("enter")
            approved = await asyncio.wait_for(task, 2)
            return prompt_seen, still_pending, approved

    assert asyncio.run(_drive()) == (True, True, True)


def test_tui_approval_resolves_from_real_message_path() -> None:
    """回归：消息经 handler→worker 执行，审批挂起时输入 y 必须能决断。

    handler 内联 await 整轮执行会阻塞消息泵（y 永远送不到 → 假死），
    本测试走真实 Input.Submitted 路径防回归（超时即失败）。
    """
    from core.loop import LoopResult  # noqa: PLC0415 — 流式事件构造

    channel = ApprovalChannel()

    class _ApprovalLoop:
        """astream 中途经审批通道挂起（模拟 web_fetch 确认门）。"""

        async def astream(self, user_input: str, *, session_id: str = ""):
            yield LoopEvent("loop_started", {"trace_id": "t1"})
            approved = await channel.ask("tools.web_fetch", {"url": "https://x"}, "出站抓取")
            yield LoopEvent("reply_delta", {"text": "已批准" if approved else "被拒绝"})
            yield LoopEvent("loop_finished", LoopResult(reply="ok", trace_id="t1"))

    api = UIAPILayer(loop=_ApprovalLoop(), approval=channel)
    api.set_llm_config(_llm())
    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    app = build_app(api)

    async def _drive() -> tuple[bool, bool]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            inp.value = "抓一下"
            await pilot.press("enter")  # 真实路径：handler 派发 worker，审批挂起
            await pilot.pause()
            prompt_seen = "需审批" in _timeline_text(app)
            inp.value = "y"
            await pilot.press("enter")  # 审批决断
            for _ in range(50):  # 等 worker 收尾（终态全文落时间线）
                await pilot.pause(0.05)
                if not app._turn_busy and app._approval_future is None:
                    break
            return prompt_seen, "已批准" in _timeline_text(app)

    assert asyncio.run(asyncio.wait_for(_drive(), 10)) == (True, True)


# ---- 任务编排入口（TUI /task 与 CLI task 共用编排器） ----


class _TaskOrchestrator:
    """编排器桩：记录目标与注入面，依序回放任务进度事件。"""

    def __init__(self, events: list[tuple[str, dict]]) -> None:
        self._events = events
        self.goals: list[str] = []

    async def astream(self, task_id: str, goal: str, **kwargs: object):
        self.goals.append(goal)
        for kind, payload in self._events:
            yield LoopEvent(kind, payload)


def _collect_task(api: UIAPILayer, session_id: str, goal: str) -> list[Event]:
    async def _run() -> list[Event]:
        return [event async for event in api.run_task(session_id, goal)]

    return asyncio.run(_run())


def test_run_task_streams_mapped_task_events() -> None:
    orch = _TaskOrchestrator(
        [
            ("task_started", {"task_id": "t1", "goal": "复合目标"}),
            ("plan_ready", {"subtasks": [{"id": "1"}], "waves": [["1"]]}),
            ("task_finished", {"outcomes": []}),
        ]
    )
    api = UIAPILayer(orchestrator=orch)
    session_id = api.create_session("cli")

    events = _collect_task(api, session_id, "复合目标")

    assert [e.type for e in events] == [
        "task.task_started",
        "task.plan_ready",
        "task.task_finished",
    ]
    assert events[0].payload["task_id"] == "t1"  # type: ignore[index]
    assert orch.goals == ["复合目标"]


def test_run_task_requires_orchestrator() -> None:
    api = UIAPILayer()
    session_id = api.create_session("cli")

    with pytest.raises(UiError) as err:
        _collect_task(api, session_id, "目标")

    assert err.value.code == UiErrorCode.UI_ORCHESTRATOR_UNSET


def test_run_task_unknown_session() -> None:
    api = UIAPILayer(orchestrator=_TaskOrchestrator([]))

    with pytest.raises(UiError) as err:
        _collect_task(api, "nope", "目标")

    assert err.value.code == UiErrorCode.UI_SESSION_NOT_FOUND


# ---- 会话维度：透传 / 压实 / 按会话读取（spec：三模统一内核启动） ----


class _SessionSpyLoop:
    """记录 astream 收到的会话标识的 loop 替身。"""

    def __init__(self) -> None:
        self.sessions: list[str] = []

    async def astream(self, user_input: str, *, session_id: str = ""):
        self.sessions.append(session_id)
        yield LoopEvent("loop_finished", {"reply": "done"})


class _MemorySpy:
    """记录 compact 实参、按写入顺序返回条目的记忆替身。"""

    def __init__(self, entries: list[MemoryEntry]) -> None:
        self._entries = entries
        self.compacted: list[tuple[str, str]] = []  # (query, session_id)
        self.reads: list[tuple[str, int]] = []

    def read(self, query: str, budget: int = 0) -> list[MemoryEntry]:
        self.reads.append((query, budget))
        return list(self._entries)

    def write(self, layer: str, entry: MemoryEntry) -> str:
        return entry.id

    def compact(self, query: str = "", budget: int = 4096, *, session_id: str = "") -> None:
        self.compacted.append((query, session_id))


def _entry(entry_id: str, session_id: str, content: str) -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=["loop"],
        source="loop",
        trace_id=f"t-{entry_id}",
        session_id=session_id,
    )


def test_run_loop_passes_session_id_to_loop() -> None:
    """API 层生成的会话标识无改写透传至内核循环。"""
    spy = _SessionSpyLoop()
    api = UIAPILayer(loop=spy)  # type: ignore[arg-type]
    api.set_llm_config(_llm())
    session_id = api.create_session("cli")
    _collect(api, session_id, "你好")
    assert spy.sessions == [session_id]


def test_compact_triggers_store_compaction() -> None:
    """compact(session_id) 触发存储层真实压实（非 no-op），且 session_id **走关键字收窄形参**。"""
    spy = _MemorySpy([])
    api = UIAPILayer(memory=spy)  # type: ignore[arg-type]
    session_id = api.create_session("cli")
    api.compact(session_id)
    # 收窄形参（change `0131` / ADR-0124）：session_id 不是 query —— 传成 query 会压实全库
    assert spy.compacted == [("", session_id)]


def test_get_memory_filters_by_session() -> None:
    """get_memory 只返回归属该会话的条目（其他会话与未归属条目不可见）。"""
    spy = _MemorySpy(
        [
            _entry("a", "s-1", "本会话记忆"),
            _entry("b", "s-2", "他会话记忆"),
            _entry("c", "", "未归属记忆"),
        ]
    )
    api = UIAPILayer(memory=spy)  # type: ignore[arg-type]
    session_id = api.create_session("cli")
    assert api.get_memory(session_id) == {"entries": []}
    spy._entries.append(_entry("d", session_id, "归属本会话"))
    assert api.get_memory(session_id) == {"entries": ["归属本会话"]}


# ---- 宠物控制面（change 0088 / 用户诉求①） ----


def _pet_control_with(session_id: str) -> PetControl:
    manager = PetManager()
    pet = PetSession(session_id=session_id)
    pet.start(PetTask(kind=PetTaskKind.IDLE_EXPLORATION, goal="观察环境"))
    manager.register(pet)
    return PetControl(manager)


def test_ui_pet_command_delegates_to_control() -> None:
    """`UIAPILayer.pet_command`（前台 `/pet [cmd]` 落点）落到注入的同一 `PetControl`。"""
    api = UIAPILayer(pet_control=_pet_control_with("p1"))
    assert api.pet_command("status", session_id="p1")["session_id"] == "p1"
    api.pet_command("sleep", session_id="p1")
    assert api.pet_command("status", session_id="p1")["sleeping"] is True


def test_ui_pet_command_without_control_raises() -> None:
    with pytest.raises(UiError) as exc_info:
        UIAPILayer().pet_command("status")
    assert exc_info.value.code is UiErrorCode.UI_PET_UNSET


# ---- 会话注册表（change 0094：跨实例共享 / 默认内存 / 枚举） ----


def test_shared_registry_session_cross_instance(tmp_path) -> None:
    """注入同一落盘注册表 ⇒ 另一实例（模拟另一进程）认该会话。"""
    registry = SessionRegistry(path=tmp_path / "conversations.json")
    session_id = UIAPILayer(loop=FakeLoop([]), registry=registry).create_session("cli")

    other = UIAPILayer(loop=FakeLoop([]), registry=registry)

    assert other.get_memory(session_id) == {"entries": []}


def test_default_registry_is_memory_only() -> None:
    """缺省装配（无 `registry=`）仍是内存注册表：他实例拒未知会话。"""
    session_id = UIAPILayer(loop=FakeLoop([])).create_session("cli")

    with pytest.raises(UiError) as exc_info:
        UIAPILayer(loop=FakeLoop([])).get_memory(session_id)
    assert exc_info.value.code is UiErrorCode.UI_SESSION_NOT_FOUND


def test_list_sessions_reports_created() -> None:
    """`list_sessions` 暴露注册表条目的标识与模式。"""
    api = UIAPILayer(loop=FakeLoop([]))
    session_id = api.create_session("cli")

    assert [entry["session_id"] for entry in api.list_sessions()] == [session_id]
    assert api.list_sessions()[0]["mode"] == "cli"


# ---- 神兽三入口（change 0137 / 账本 E74） ----


class _FakeBeastSession:
    """会话替身：只承载 API 面用到的三处（`beast.agent_id` / `state.value` / `result_summary`）。"""

    def __init__(self, agent_id: str, state: str, *, reply: str | None = None) -> None:
        self.beast = SimpleNamespace(agent_id=agent_id)
        self.state = SimpleNamespace(value=state)
        self._summary: dict[str, object] = {
            "agent_id": agent_id,
            "has_result": reply is not None,
            "reply": reply,
            "failed": False if reply is not None else None,
        }

    def result_summary(self) -> dict[str, object]:
        return dict(self._summary)


class _FakeBeastActivator:
    """记录落点的激活器替身（证明 verb 落到同一 activator 的对应入口）。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def activate_from_slash(self, target: str, task: str = "") -> _FakeBeastSession:
        self.calls.append(("summon", f"{target}|{task}"))
        return _FakeBeastSession("beast.qinglong", "recalled", reply="青龙蓝图已出")

    def recall_from_slash(self, target: str) -> _FakeBeastSession:
        self.calls.append(("recall", target))
        return _FakeBeastSession("beast.qinglong", "recalled")

    async def activate_from_nl(self, user_input: str) -> _FakeBeastSession:
        self.calls.append(("nl", user_input))
        return _FakeBeastSession("beast.qinglong", "recalled", reply="蓝图")


def _beast_api(activator: object) -> UIAPILayer:
    return UIAPILayer(beast_activator=cast(Any, activator))


def test_ui_beast_command_without_activator_raises() -> None:
    """未注入 ⇒ `UI_BEAST_UNSET`（与 pet 同型，fail-explicit 不静默）。"""
    with pytest.raises(UiError) as exc_info:
        asyncio.run(UIAPILayer().beast_command("summon", "青龙"))
    assert exc_info.value.code is UiErrorCode.UI_BEAST_UNSET


def test_ui_activate_beast_without_activator_raises() -> None:
    """WebUI 自然语言入口未接 ⇒ `UI_BEAST_UNSET`。"""
    with pytest.raises(UiError) as exc_info:
        asyncio.run(UIAPILayer().activate_beast("召唤青龙 架构设计"))
    assert exc_info.value.code is UiErrorCode.UI_BEAST_UNSET


def test_ui_beast_command_unknown_verb_raises() -> None:
    with pytest.raises(UiError) as exc_info:
        asyncio.run(_beast_api(_FakeBeastActivator()).beast_command("banish", "青龙"))
    assert exc_info.value.code is UiErrorCode.UI_BEAST_UNKNOWN_VERB


def test_ui_beast_command_unknown_beast_reports_ui_error() -> None:
    """无匹配神兽：领域错误在 API 边界归一为 `UI_BEAST_NOT_FOUND`（不向 UI 抛裸异常）。"""
    with pytest.raises(UiError) as exc_info:
        asyncio.run(_beast_api(BeastActivator()).beast_command("summon", "没有这只兽"))
    assert exc_info.value.code is UiErrorCode.UI_BEAST_NOT_FOUND


def test_ui_beast_command_dormant_recall_reports_ui_error() -> None:
    """无在岗可召回（`BEAST_NOT_MANIFEST`）⇒ `UI_BEAST_STATE_INVALID`（与「无此兽」分码）。"""
    with pytest.raises(UiError) as exc_info:
        asyncio.run(_beast_api(BeastActivator()).beast_command("recall", "青龙"))
    assert exc_info.value.code is UiErrorCode.UI_BEAST_STATE_INVALID


def test_ui_beast_command_delegates_to_activator() -> None:
    """`/summon` 落到 `activate_from_slash`（带 task）、`/recall` 落到 `recall_from_slash`。"""
    activator = _FakeBeastActivator()
    api = _beast_api(activator)

    summon = asyncio.run(api.beast_command("summon", "青龙", task="架构设计"))
    recall = asyncio.run(api.beast_command("recall", "青龙"))

    assert activator.calls == [("summon", "青龙|架构设计"), ("recall", "青龙")]
    assert summon["agent_id"] == "beast.qinglong"
    assert summon["state"] == "recalled"
    assert summon["has_result"] is True and summon["reply"] == "青龙蓝图已出"
    assert recall["has_result"] is False  # 召回不编造结果正文


def test_ui_activate_beast_returns_session_id() -> None:
    """WebUI 自然语言入口返回会话 id（对称 `activate_pet`）。"""
    activator = _FakeBeastActivator()

    agent_id = asyncio.run(_beast_api(activator).activate_beast("召唤青龙 架构设计"))

    assert agent_id == "beast.qinglong"
    assert activator.calls == [("nl", "召唤青龙 架构设计")]


def test_tui_summon_and_recall_slash_commands() -> None:
    """TUI `/summon` `/recall`：状态行落时间线，结果**有才打印**（change 0137）。"""
    pytest.importorskip("textual")
    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    activator = _FakeBeastActivator()
    app = build_app(_beast_api(activator))

    async def _drive() -> str:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            inp.value = "/summon qinglong 架构设计"
            await pilot.press("enter")
            await pilot.pause()
            inp.value = "/recall qinglong"
            await pilot.press("enter")
            await pilot.pause()
            return _timeline_text(app)

    text = asyncio.run(_drive())
    assert activator.calls == [("summon", "qinglong|架构设计"), ("recall", "qinglong")]
    assert "已召唤神兽 beast.qinglong（状态 recalled）" in text
    assert "结果（成功）：青龙蓝图已出" in text
    assert "已召回神兽 beast.qinglong（状态 recalled）" in text


def test_tui_summon_usage_hint_on_missing_target() -> None:
    """`/summon` 无目标 ⇒ 用法提示，不发起激活（不吞参数错误）。"""
    pytest.importorskip("textual")
    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    activator = _FakeBeastActivator()
    app = build_app(_beast_api(activator))

    async def _drive() -> str:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            inp.value = "/summon"
            await pilot.press("enter")
            await pilot.pause()
            return _timeline_text(app)

    text = asyncio.run(_drive())
    assert activator.calls == []
    assert "用法：/summon <神兽> [任务] ｜ /recall <神兽>" in text
