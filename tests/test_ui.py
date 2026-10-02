"""ui 单元测试（对齐契约红线：三模复用 / SSE 流式 / 四错误码 / LLM key 只存引用）。"""

from __future__ import annotations

import asyncio

import pytest

from core.configuration.models import LLMConfig
from core.loop import LoopEvent
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
