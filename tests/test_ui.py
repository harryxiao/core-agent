"""ui 单元测试（对齐契约红线：三模复用 / SSE 流式 / 四错误码 / LLM key 只存引用）。"""

from __future__ import annotations

import asyncio

import pytest

from core.configuration.models import LLMConfig
from core.loop import LoopEvent
from core.permission import ApprovalChannel
from core.ui import CLIBridge, DesktopBridge, Event, UIAPILayer, UiError, UiErrorCode, WebBridge


class FakeLoop:
    """产出受控 LoopEvent 流的 loop 替身。"""

    def __init__(self, events: list[LoopEvent]) -> None:
        self._events = events

    async def astream(self, user_input: str):
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
    CLIBridge(api=api, connect_impl=connected.append).connect()
    assert connected == [api]
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


# ---- TUI（ReplApp headless 冒烟）----


def _tui_app() -> object:
    pytest.importorskip("textual")
    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    api, _ = _streaming_api()
    return build_app(api)


def _timeline_text(app: object) -> str:
    """时间线全量文本：Static 取渲染文本，Collapsible 取标题 + 内部 Static。"""
    from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
    from textual.widgets import Collapsible, Static  # noqa: PLC0415 — 可选依赖懒 import

    parts: list[str] = []
    for child in app.query_one("#timeline", Vertical).children:
        if isinstance(child, Collapsible):
            parts.append(str(child.title))
            parts.extend(str(s.render()) for s in child.query(Static))
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


def test_tui_message_roundtrip_clears_status() -> None:
    app = _tui_app()

    async def _drive() -> tuple[bool, object]:
        from textual.widgets import Input, Static  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            inp.value = "hi"
            await pilot.press("enter")
            await pilot.pause()
            running = app.is_running
            status = app.query_one("#status", Static).content
            input_cleared = inp.value == ""
        return running and input_cleared, status

    ok, status = asyncio.run(_drive())
    assert ok is True
    assert status == ""


def test_tui_streams_deltas_then_flushes_once() -> None:
    """流式 reply_delta：live 区逐字上屏，终态全文只落日志一次（不重复）。"""
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

    async def _drive() -> tuple[bool, int]:
        from textual.widgets import Input, Static  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            inp.value = "hi"
            await pilot.press("enter")
            await pilot.pause()
            live_hidden = app.query_one("#live", Static).display is False
            log_text = _timeline_text(app)
            running = app.is_running
        return live_hidden and running, log_text.count("你好")

    ok, count = asyncio.run(_drive())
    assert ok is True
    assert count == 1  # 全文只出现一次（live 流式落定，终态不重复）


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

        async def astream(self, user_input: str):
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
