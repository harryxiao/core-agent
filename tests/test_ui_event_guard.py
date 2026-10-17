"""TUI 点击与流式 Markdown 换段竞态兜底（change 0238）。

textual#6643：`Markdown.update()` 换段瞬间，compositor 命中测试仍可能返回已从 DOM
摘除的段落（`parent=None`）⇒ `Screen._forward_event` 的选择初始化对 `container.region`
解引用 ⇒ `AttributeError` 整应用崩溃。上游最新版（8.2.8）未修 ⇒ 在 `ReplApp.on_event`
边界丢弃该单个事件；守卫只收 `AttributeError`，真缺陷仍照常冒泡。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from textual import events
from textual.geometry import Offset
from textual.widgets import Static

from core.configuration.models import LLMConfig
from core.loop import LoopEvent
from core.ui import UIAPILayer
from core.ui.repl import build_app


def _llm() -> LLMConfig:
    return LLMConfig(provider="openai", model="gpt-4o", endpoint="https://x", api_key_ref="${K}")


class _EchoLoop:
    """回显 loop 替身：一次性收尾。"""

    async def astream(self, user_input: str, *, session_id: str = ""):
        yield LoopEvent("loop_finished", {"reply": f"echo:{user_input}"})


def _app() -> Any:
    api = UIAPILayer(loop=_EchoLoop())
    api.set_llm_config(_llm())
    return build_app(api)


def _mouse_down() -> events.MouseDown:
    return events.MouseDown(
        widget=None,
        x=5,
        y=5,
        delta_x=0,
        delta_y=0,
        button=1,
        shift=False,
        meta=False,
        ctrl=False,
        screen_x=5,
        screen_y=5,
    )


def test_click_hit_detached_widget_survives(monkeypatch: pytest.MonkeyPatch) -> None:
    """承重：命中测试返回已摘除 widget（textual#6643 竞态形态）⇒ 应用不崩。"""
    app = _app()

    async def drive() -> None:
        async with app.run_test():
            detached = Static("x")  # 从未挂载 ⇒ parent=None（同崩溃形态）
            monkeypatch.setattr(
                app.screen, "get_widget_and_offset_at", lambda x, y: (detached, Offset(0, 0))
            )
            await app.on_event(_mouse_down())  # 无守卫 ⇒ AttributeError 冒泡

    asyncio.run(drive())


def test_events_still_forwarded_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """守卫透明：正常事件恰转发一次（无吞、无重派）。"""
    app = _app()

    async def drive() -> None:
        async with app.run_test():
            seen: list[object] = []
            monkeypatch.setattr(app.screen, "_forward_event", lambda ev: seen.append(ev))
            await app.on_event(_mouse_down())
            assert len(seen) == 1

    asyncio.run(drive())


def test_real_errors_still_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    """守卫只收 AttributeError：真缺陷（RuntimeError）照常冒泡（不吞 turn 语义）。"""
    app = _app()

    async def drive() -> None:
        async with app.run_test():

            def _boom(_ev: object) -> None:
                raise RuntimeError("boom")

            monkeypatch.setattr(app.screen, "_forward_event", _boom)
            with pytest.raises(RuntimeError):
                await app.on_event(_mouse_down())

    asyncio.run(drive())
