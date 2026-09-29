"""Textual REPL 适配器（ui 接入层边界依赖）。

CLIBridge.connect() 落地为 Textual 交互会话循环；textual 仅此文件持有且懒 import
（ADR-0040 MAL 隔离），上层（cli_bridge / UIAPILayer）不依赖具体 TUI 框架。

对应接口：doc/03-interfaces/ui-interface.md §1（CLIBridge 交互会话面）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from .api import UIAPILayer
from .errors import UiError
from .models import Event


async def repl_loop(
    api: UIAPILayer,
    session_id: str,
    *,
    read: Callable[[], Awaitable[str | None]],
    write: Callable[[Event], Awaitable[None]],
) -> None:
    """REPL 核心循环（纯逻辑，可测）：多轮复用同一会话，空输入/EOF 退出。"""
    while True:
        line = await read()
        if line is None or not line.strip():
            return
        try:
            async for event in api.run_loop(session_id, line):
                await write(event)
        except UiError as err:
            await write(_error_event(err))


def barge_in_event(api: UIAPILayer) -> Event:
    """barge-in 动作兜底：TTS 未接时 UiError 降级为 error 事件（不抛裸异常）。"""
    try:
        api.barge_in()
    except UiError as err:
        return _error_event(err)
    return Event(type="barge_in", payload={"ok": True})


def _error_event(err: UiError) -> Event:
    """UiError → 结构化 error 事件（不向 TUI 抛裸异常）。"""
    return Event(type="error", payload={"code": err.code.value, "message": err.message})


def build_app(api: UIAPILayer) -> Any:
    """构建 Textual 应用（懒 import textual），暴露给 headless 冒烟测试驱动。"""
    from textual.app import App, ComposeResult  # noqa: PLC0415 — MAL 懒 import
    from textual.widgets import Input, RichLog  # noqa: PLC0415 — MAL 懒 import

    session_id = api.create_session("cli")

    class ReplApp(App[None]):
        """core-agent 交互会话 TUI。"""

        BINDINGS = [("ctrl+b", "barge_in", "打断")]

        def compose(self) -> ComposeResult:
            yield RichLog(id="output")
            yield Input(placeholder="> ", id="input")

        def on_mount(self) -> None:
            self.query_one("#input", Input).focus()

        def action_barge_in(self) -> None:
            self.query_one("#output", RichLog).write(_format_event(barge_in_event(api)))

        async def on_input_submitted(self, message: Input.Submitted) -> None:
            log = self.query_one("#output", RichLog)
            text = message.value.strip()
            if not text:
                self.exit()
                return
            log.write(f"> {text}")
            try:
                async for event in api.run_loop(session_id, text):
                    log.write(_format_event(event))
            except UiError as err:
                log.write(_format_event(_error_event(err)))

    return ReplApp()


def run_repl(api: UIAPILayer) -> None:
    """启动 Textual 交互会话循环（阻塞；懒 import textual）。"""
    build_app(api).run()


def _format_event(event: Event) -> str:
    """Event → 单行文本（REPL 输出）。"""
    if event.type == "error":
        payload = cast(dict[str, object], event.payload)
        return f"[{payload.get('code', 'error')}] {payload.get('message', '')}"
    return str(event.payload)
