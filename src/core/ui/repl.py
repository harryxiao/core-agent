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
    from textual.containers import Horizontal  # noqa: PLC0415 — MAL 懒 import
    from textual.widgets import Input, RichLog, Static  # noqa: PLC0415 — MAL 懒 import

    session_id = api.create_session("cli")

    class ReplApp(App[None]):
        """core-agent 交互会话 TUI。"""

        CSS = """
#input-row {
    height: auto;
}
#prompt {
    width: auto;
}
#input {
    width: 1fr;
    height: 1;
    border: none;
    padding: 0;
}
"""

        BINDINGS = [("ctrl+b", "barge_in", "打断")]

        def compose(self) -> ComposeResult:
            yield RichLog(id="output")
            with Horizontal(id="input-row"):
                yield Static("> ", id="prompt")
                yield Input(placeholder="输入消息，回车发送（Ctrl+B 打断）", id="input")

        def on_mount(self) -> None:
            self.query_one("#input", Input).focus()

        def action_barge_in(self) -> None:
            line = _format_event(barge_in_event(api))
            if line:
                self.query_one("#output", RichLog).write(line)

        async def on_input_submitted(self, message: Input.Submitted) -> None:
            log = self.query_one("#output", RichLog)
            text = message.value.strip()
            message.input.clear()  # 回车即清空输入框，准备下一轮
            if not text:
                self.exit()
                return
            log.write(f"> {text}")
            try:
                async for event in api.run_loop(session_id, text):
                    line = _format_event(event)
                    if line:
                        log.write(line)
            except UiError as err:
                log.write(_format_event(_error_event(err)))

    return ReplApp()


def run_repl(api: UIAPILayer) -> None:
    """启动 Textual 交互会话循环（阻塞；懒 import textual）。"""
    build_app(api).run()


def _format_event(event: Event) -> str | None:
    """Event → 单行文本；None 表示内部脚手架事件（会话/回合/结果对象），不显示。

    只回显交互内容：错误（error/loop.error）与回复文本（loop.result 的 text/reply），
    剥离 session_id/trace_id/round/LoopResult 等后端事件。
    """
    payload = event.payload
    if event.type == "error":
        data = cast(dict[str, object], payload)
        return f"[{data.get('code', 'error')}] {data.get('message', '')}"
    if event.type == "loop.error":
        data = cast(dict[str, object], payload) if isinstance(payload, dict) else {}
        return f"[loop.error] {data.get('reason', '')}"
    if event.type == "loop.result" and isinstance(payload, dict):
        data = cast(dict[str, object], payload)
        text = data.get("text") or data.get("reply")
        return str(text) if text else None
    return None
