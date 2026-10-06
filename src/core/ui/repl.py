"""Textual REPL 适配器（ui 接入层边界依赖）。

CLIBridge.connect() 落地为 Textual 交互会话循环；textual 仅此文件持有且懒 import
（ADR-0040 MAL 隔离），上层（cli_bridge / UIAPILayer）不依赖具体 TUI 框架。

对标 Claude CLI 的呈现层：
- core 主题（terracotta accent #d97757）+ 圆角输入框（focus 高亮）；
- 输入区/提示盒整体钉底（dock: bottom），时间线独占剩余高度（防 1fr 撑满）；
- 工作状态行 ✻ label… (Ns)（set_interval 轮换 glyph，无内置 Spinner 组件）；
- 回复流式增量直接落时间线尾部同一滚动流（连续滚动输出，视口跟随），每段即按
  Markdown 增量渲染（标题/代码高亮流式即所见），段边界固化 append-only，
  终态无整块替换、无重排跳变；
- 用户输入以 ❯ 前缀行回显；底部快捷键提示盒（F1 展开）；启动欢迎横幅；
- 任务/子任务进度走折叠块（单行提示 + 展开详情）。

对应接口：doc/03-interfaces/ui-interface.md §1（CLIBridge 交互会话面）。
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from .api import UIAPILayer
from .errors import UiError
from .models import Event

_ACCENT = "#d97757"  # core 主题 accent（Claude CLI terracotta）
_SPIN_GLYPHS = ["✻", "·", "•", "∘", "○"]  # 工作状态行轮换符号
_MS_PER_SECOND = 1000  # 耗时人类可读换算
_TAIL_SPLIT = 2000  # 流式尾段字符阈值：超过/行边界即固化（每 delta 重 wrap 有界）
_TAIL_FENCE_CAP = 8000  # 未闭合围栏内尾段硬上限：超此值强固化兜底，约束内存


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


def _event_delta(event: Event) -> str | None:
    """``loop.delta`` 增量帧 → 增量文本；其余事件返回 None。

    增量与终态**分属两型**（change `0132` / ADR-0125 / 账本 E65）：``loop.delta`` 载荷恒为
    ``{"text": …}``，终态 ``loop.result`` 载荷为 LoopResult 对象（非 dict），由
    ``_format_event`` / ``_flush_live`` 收口 —— 分流**只看类型**，不再靠载荷形状。
    """
    payload = event.payload
    if event.type != "loop.delta" or not isinstance(payload, dict):
        return None
    data = cast(dict[str, object], payload)
    return str(data.get("text", "")) or None


def format_task_event(kind: str, payload: object) -> str | None:  # noqa: PLR0911, C901 — 一分支一返回
    """编排进度事件 → 单行文本；无需展示的事件返回 None（CLI 与 TUI 共用）。"""
    if not isinstance(payload, dict):
        return None
    data = cast(dict[str, Any], payload)
    if kind == "task_started":
        return f"[task] 任务 {data.get('task_id')}：{data.get('goal', '')}"
    if kind == "plan_ready":
        n = len(data.get("subtasks", []))
        return f"[plan] 拆解 {n} 个子任务，波次 {data.get('waves')}"
    if kind == "wave_started":
        return f"[wave] 开始波次 {data.get('wave')}"
    if kind == "subtask_started":
        return f"[子任务 {data.get('subtask_id')}] {data.get('goal', '')}"
    if kind == "subtask_completed":
        if data.get("skipped"):
            return f"[子任务 {data.get('subtask_id')}] ✓ 已完成（续跑跳过）"
        mark = "✓" if data.get("ok") else "✗"
        reason = f" — {data.get('reason', '')}" if not data.get("ok") else ""
        return f"[子任务 {data.get('subtask_id')}] {mark}{reason}"
    if kind == "task_checkpoint":
        return f"[checkpoint] 波次 {data.get('wave')} 已持久化"
    if kind == "task_failed":
        return f"[task_failed] {data.get('code')}: {data.get('reason')}"
    if kind == "task_finished":
        outcomes = data.get("outcomes", [])
        ok = sum(1 for o in outcomes if getattr(o, "ok", False))
        return f"[task_finished] 任务完成（{ok}/{len(outcomes)} 子任务通过）"
    return None


_TOOL_NAMES = {  # tool_id → Claude CLI 式友好名（用户可见层不暴露内部 id/参数）
    "tools.code_run": "Bash",
    "tools.file_read": "Read",
    "tools.file_write": "Write",
    "tools.file_patch": "Edit",
    "tools.web_fetch": "WebFetch",
}


def _tool_name(tool_id: object) -> str:
    """tool_id → 友好名；未映射的去掉 tools. 前缀兜底。"""
    name = str(tool_id or "")
    mapped = _TOOL_NAMES.get(name)
    if mapped:
        return mapped
    short = name.removeprefix("tools.")
    return short or name


def _fmt_ms(ms: object) -> str:
    """毫秒 → 人类可读（<1s 显示 ms，≥1s 显示 s 一位小数）。"""
    try:
        value = int(ms)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    return f"{value / _MS_PER_SECOND:.1f}s" if value >= _MS_PER_SECOND else f"{value}ms"


def format_action_event(kind: str, payload: object) -> str | None:
    """工具动作事件 → 单行文本（CLI 与 TUI 共用）；非动作事件返回 None。"""
    if not isinstance(payload, dict):
        return None
    data = cast(dict[str, Any], payload)
    tool = _tool_name(data.get("tool_id"))
    if kind == "action_started":
        return f"⏺ {tool}"
    if kind == "action_completed":
        if data.get("ok"):
            return f"⏺ {tool} ✓ ({_fmt_ms(data.get('duration_ms'))})"
        return f"⏺ {tool} ✗"
    return None


def _format_event(event: Event) -> str | None:
    """Event → 单行文本；None 表示内部脚手架事件（会话/回合/结果对象），不显示。

    只回显交互内容：错误（error/loop.error）与增量文本（loop.delta 的 text），
    剥离 session_id/trace_id/round/LoopResult 等后端事件。
    """
    payload = event.payload
    if event.type.startswith("task."):  # 编排进度事件（CLI 同构文本，TUI 走折叠块）
        return format_task_event(event.type.removeprefix("task."), payload)
    if event.type == "error":
        data = cast(dict[str, object], payload)
        return f"[{data.get('code', 'error')}] {data.get('message', '')}"
    if event.type == "loop.error":
        data = cast(dict[str, object], payload) if isinstance(payload, dict) else {}
        return f"[loop.error] {data.get('reason', '')}"
    if event.type == "loop.delta" and isinstance(payload, dict):
        data = cast(dict[str, object], payload)
        text = data.get("text")
        return str(text) if text else None
    return None


def _parse_beast_command(text: str) -> tuple[str, str, str] | None:
    """`/summon <神兽> [任务]` · `/recall <神兽>` 解析为 `(verb, target, task)`。

    形态不合法（非本命令 / 缺目标）返回 None —— 由调用方给用法提示，不静默吞参数错误。
    """
    head, _, rest = text.partition(" ")
    if head not in ("/summon", "/recall"):
        return None
    parts = rest.split()
    if not parts:
        return None
    verb = "summon" if head == "/summon" else "recall"
    return verb, parts[0], " ".join(parts[1:])


_BEAST_USAGE = "用法：/summon <神兽> [任务] ｜ /recall <神兽>"


def build_app(api: UIAPILayer, session_id: str = "") -> Any:  # noqa: C901 — 内嵌 ReplApp 类体推高复杂度
    """构建 Textual 应用（懒 import textual），暴露给 headless 冒烟测试驱动。

    `session_id` 非空 ⇒ **续聊**既有会话（复用该标识并载入其转录；未登记 ⇒ `UiError`，
    fail-closed，不静默新建顶替）；缺省 ⇒ 新建 CLI 会话（既有行为不变）。
    """
    history: list[dict[str, Any]] = []
    if session_id:
        history = api.session_messages(session_id)  # 未登记 ⇒ UiError（先于进入 TUI 拒绝）
    else:
        session_id = api.create_session("cli")
    from rich.markup import escape  # noqa: PLC0415 — MAL 懒 import
    from textual.app import App, ComposeResult  # noqa: PLC0415 — MAL 懒 import
    from textual.containers import Horizontal, Vertical  # noqa: PLC0415 — MAL 懒 import
    from textual.theme import Theme  # noqa: PLC0415 — MAL 懒 import
    from textual.timer import Timer  # noqa: PLC0415 — MAL 懒 import
    from textual.widget import Widget  # noqa: PLC0415 — MAL 懒 import
    from textual.widgets import (  # noqa: PLC0415 — MAL 懒 import
        Collapsible,
        Input,
        Markdown,
        Static,
    )

    approval = api.approval  # 审批通道（None 表示非交互入口，confirm 门 fail-closed）
    core_theme = Theme(name="core", primary=_ACCENT, accent=_ACCENT, secondary=_ACCENT, dark=True)

    class ReplApp(App[None]):
        """core-agent 交互会话 TUI：时间线（❯ 行/Markdown/折叠块）+ 工作状态行。"""

        CSS = """
#timeline {
    height: 1fr;
    overflow-y: auto;
    padding: 0 1;
}
#panel {  /* 子 Agent 焦点视图：与时间线互斥显示（display 切换，绝不 unmount） */
    height: 1fr;
    overflow-y: auto;
    padding: 0 1;
}
#panel-title {
    color: $accent;
    text-style: bold;
}
#footer {  /* 输入区+提示盒钉底：时间线独占剩余空间（内层容器默认 1fr 会撑满全屏） */
    dock: bottom;
    height: auto;
}
#input-box {
    height: auto;
    border: round $panel;
    padding: 0 1;
    margin: 0 1;
}
#input-box:focus-within {
    border: round $accent;
}
#prompt {
    width: auto;
    color: $accent;
    text-style: bold;
}
#input {
    width: 1fr;
    height: 1;
    border: none;
    padding: 0;
}
#hints {
    border: round $panel;
    width: auto;
    padding: 0 2;
    margin: 0 1;
    color: $text-muted;
    align: center middle;
}
#spinner {
    height: 1;
    width: auto;
    padding: 0 2;
    color: $text-muted;
}
.echo {  /* 用户输入回显：❯ 前缀行（accent 前缀经 markup） */
    color: $text;
    width: auto;
    padding: 0 1;
    margin: 0 0 0 0;
}
.hint {  /* 系统/进度提示：浅灰单行 */
    color: $text-muted;
    width: auto;
}
.ok {
    color: $success;
    width: auto;
    text-style: bold;
}
.fail {
    color: $error;
    width: auto;
}
.welcome {  /* 启动横幅 */
    border: round $panel;
    padding: 0 1;
    margin: 0 1 1 1;
    color: $text-muted;
}
Collapsible {  /* 子任务/工具动作：单行提示，点击展开 */
    background: transparent;
    border: none;
    padding: 0;
    width: 1fr;
    height: auto;
}
Collapsible > CollapsibleTitle {
    color: $text-muted;
    background: transparent;
    padding: 0 1;
}
Collapsible > CollapsibleTitle:hover {
    background: $panel;
}
"""

        # 退出走 App 默认 ctrl+q / ctrl+c；空回车不再退出（IME 确认等误触防护）
        BINDINGS = [
            ("ctrl+b", "barge_in", "打断"),
            ("f1", "hints", "快捷键"),
            ("f2", "focus_main", "返回主视图"),
        ]

        _HINTS_SHORT = "F1 快捷键 · Ctrl+B 打断 · Ctrl+Q 退出 · /focus 子任务 聚焦 · F2 返回主视图"
        _HINTS_FULL = (
            "F1 快捷键 · Ctrl+B 打断 · Ctrl+Q 退出 · /task <目标> 启动编排 · "
            "/focus <子任务> 聚焦 · /main 或 F2 返回主视图 · "
            "审批 y 批准 / n 拒绝 · 点击子任务/动作行展开详情"
        )

        def __init__(self) -> None:
            super().__init__()
            self._live_buf: list[str] = []  # 流式全文缓冲（终态取 _last_reply）
            self._tail_buf: list[str] = []  # 进行中尾段增量（每 delta 热更新）
            self._tail_widget: Markdown | None = None  # 尾段渲染块
            self._last_reply: str = ""  # 终态回复原文（Markdown 无公开源文本取口）
            self._approval_future: Any | None = None  # 挂起中的审批 Future[bool]
            self._turn_busy = False  # 本轮 worker 是否在跑（忙时新消息提示等待）
            self._open: dict[str, tuple[Collapsible, Static, str]] = {}  # sid→(块, 详情, goal)
            self._focus_sid: str = ""  # 焦点中的子任务标识（"" = 主视图）
            self._focus_box: Collapsible | None = None  # 焦点折叠块（身份绑定：sid 跨任务复用）
            self._focus_detail: Static | None = None  # 焦点折叠块详情（面板正文取此渲染文本）
            self._actions: dict[str, tuple[Collapsible, Static]] = {}  # round:tool→(块, 详情)
            self._reasoning: tuple[Collapsible, Static] | None = None  # 本轮思考块（同轮归并）
            self._spin_timer: Timer | None = None  # 工作状态行驱动
            self._spin_t0 = 0.0
            self._spin_idx = 0
            self._spin_label = ""
            self._hints_on = False

        def compose(self) -> ComposeResult:
            yield Vertical(id="timeline")
            with Vertical(id="panel"):  # 子 Agent 焦点视图（初始隐藏，见 on_mount）
                yield Static(id="panel-title")
                yield Static("", id="panel-body", classes="hint", markup=False)
            yield Static(id="spinner")
            with Vertical(id="footer"):  # 输入区+提示盒钉底，时间线独占剩余空间
                with Horizontal(id="input-box"):
                    yield Static("❯ ", id="prompt")
                    yield Input(placeholder="发送消息，或 /task <目标> 启动编排任务", id="input")
                yield Static(self._HINTS_SHORT, id="hints")

        def on_mount(self) -> None:
            self.register_theme(core_theme)
            self.theme = "core"
            self.query_one("#spinner", Static).display = False
            self.query_one("#panel", Vertical).display = False  # 初始主视图（命令式置隐）
            self.query_one("#input", Input).focus()
            self._add(
                Static(
                    f"[{_ACCENT}]◍ core-agent[/] 已就绪\n"
                    "/task <目标> 启动编排任务 · 高风险动作需 y/n 审批 · 点击折叠行展开详情",
                    classes="welcome",
                    markup=True,
                )
            )
            if approval is not None:
                approval.handler = self._ask_approval  # 审批通道接终端 y/n
            if history:  # 续聊：把既有转录铺进时间线（否则界面空白、看不出已接上）
                self._add(
                    Static(f"↻ 续接会话 {session_id}（{len(history)} 条历史已载入）", classes="ok")
                )
                for item in history:
                    content = escape(str(item.get("content", "")))
                    if item.get("role") == "user":
                        self._add(Static(f"[{_ACCENT}]❯[/] {content}", classes="echo", markup=True))
                    else:
                        self._add(Static(content, classes="hint", markup=False))

        # ---- 时间线 ----

        def _add(self, widget: Widget) -> None:
            """时间线追加 widget 并滚到底（mount 不等待，消息泵不被阻塞）。"""
            timeline = self.query_one("#timeline", Vertical)
            timeline.mount(widget)
            timeline.call_after_refresh(timeline.scroll_end, animate=False)

        # ---- 工作状态行（✻ label… (Ns)，Claude CLI 式自转） ----

        def _spin_start(self, label: str) -> None:
            """启动（或改标签）工作状态行：glyph 轮换 + 秒计时。"""
            if self._spin_timer is None:
                self._spin_t0 = time.monotonic()
                self._spin_timer = self.set_interval(0.12, self._spin_tick)
            self._spin_label = label
            self.query_one("#spinner", Static).display = True

        def _spin_tick(self) -> None:
            """轮换 glyph 并刷新计时（timer 驱动，不阻塞消息泵）。"""
            self._spin_idx = (self._spin_idx + 1) % len(_SPIN_GLYPHS)
            elapsed = int(time.monotonic() - self._spin_t0)
            glyph = _SPIN_GLYPHS[self._spin_idx]
            self.query_one("#spinner", Static).update(f"{glyph} {self._spin_label}… ({elapsed}s)")

        def _spin_relabel(self, label: str) -> None:
            """仅在运行中改标签（审批挂起等场景），不重启计时。"""
            if self._spin_timer is not None:
                self._spin_label = label

        def _spin_stop(self) -> None:
            """停止并隐藏工作状态行（回合收尾）。"""
            if self._spin_timer is not None:
                self._spin_timer.stop()
                self._spin_timer = None
            self.query_one("#spinner", Static).display = False

        async def _ask_approval(self, tool_id: str, args: dict[str, Any], reason: str) -> bool:
            """审批提示落时间线，输入 y/n 决断；同刻仅一单（重复请求 fail-closed）。"""
            self._set_focus("")  # 审批提示须可见（否则挂起提示落进被隐藏的时间线）
            if self._approval_future is not None and not self._approval_future.done():
                return False
            import asyncio  # noqa: PLC0415 — 与 textual 懒 import 同策略

            future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
            self._approval_future = future
            self._add(Static(f"⚠ 需审批: {reason}", classes="fail", markup=False))
            self._add(Static("输入 y 批准 / n 拒绝", classes="hint"))
            self._spin_relabel("等待审批")
            try:
                return await future
            finally:
                self._approval_future = None
                self._spin_relabel("思考中")

        def action_barge_in(self) -> None:
            line = _format_event(barge_in_event(api))
            if line:
                self._add(Static(line, classes="hint", markup=False))

        def action_hints(self) -> None:
            """F1 切换底部快捷键提示盒（短行 ↔ 完整列表）。"""
            self._hints_on = not self._hints_on
            text = self._HINTS_FULL if self._hints_on else self._HINTS_SHORT
            self.query_one("#hints", Static).update(text)

        def _show_delta(self, delta: str) -> None:
            """流式增量落时间线同一滚动流：尾段热更新（有界 wrap），
            行边界/超阈值时固化为 append-only 块，超长输出不卡顿不抖动；
            代码围栏未闭合时延后固化，避免大代码块被拆断。"""
            self._live_buf.append(delta)
            self._tail_buf.append(delta)
            text = "".join(self._tail_buf)
            if self._in_open_fence(text):
                # 围栏未闭合：不按行/常规阈值固化（避免大代码块被拦腰截断），
                # 仅超硬上限时兜底固化，约束内存与重 wrap 代价
                if len(text) >= _TAIL_FENCE_CAP:
                    self._freeze_tail(text)
                    return
                self._touch_tail(text)
                return
            if len(text) >= _TAIL_SPLIT or text.endswith("\n"):
                self._freeze_tail(text)
                return
            self._touch_tail(text)

        @staticmethod
        def _in_open_fence(text: str) -> bool:
            """尾段是否处于未闭合代码围栏内（行首 ``` / ~~~ 数量为奇数）。"""
            fences = sum(1 for line in text.split("\n") if line.lstrip().startswith(("```", "~~~")))
            return fences % 2 == 1

        def _touch_tail(self, text: str) -> None:
            """尾段热更新：Markdown 增量渲染（与终态同格式，无替换跳变），
            仅重解析有界尾文本，视口跟随滚动。"""
            if self._tail_widget is None:
                self._tail_widget = Markdown(text)
                self._add(self._tail_widget)  # _add 已带 scroll_end
                return
            self._tail_widget.update(text)
            timeline = self.query_one("#timeline", Vertical)
            timeline.call_after_refresh(timeline.scroll_end, animate=False)

        def _freeze_tail(self, text: str) -> None:
            """尾段固化：当前尾块补齐内容后冻结（不再重渲染），缓冲复位。
            固化块同为 Markdown（流式即所见终态样式，append-only 不重排）。"""
            if self._tail_widget is not None:
                self._tail_widget.update(text)
            elif text:
                widget = Markdown(text)
                self._add(widget)
            self._tail_widget = None
            self._tail_buf = []
            timeline = self.query_one("#timeline", Vertical)
            timeline.call_after_refresh(timeline.scroll_end, animate=False)

        def _flush_live(self) -> None:
            """流式终态：尾段固化为最后一块 Markdown，已固化块原样保留。
            全程同格式渲染，无终态整块替换、无重排跳变。"""
            if self._tail_buf:
                self._freeze_tail("".join(self._tail_buf))
            self._last_reply = "".join(self._live_buf)
            self._tail_widget = None
            self._tail_buf = []
            self._live_buf = []

        # ---- 输入分发 ----

        def on_input_submitted(self, message: Input.Submitted) -> None:
            """输入分发：审批决断优先；消息经 worker 执行（消息泵不被阻塞）。"""
            pending = self._approval_future
            if pending is not None and not pending.done():
                # 审批决断分支：y 批准 / n 拒绝；其他输入提示重输
                message.input.clear()
                answer = message.value.strip().lower()
                if answer in ("y", "yes", "n", "no"):
                    self._add(
                        Static(f"[{_ACCENT}]❯[/] {escape(answer)}", classes="echo", markup=True)
                    )
                    pending.set_result(answer in ("y", "yes"))
                else:
                    self._add(Static("请输入 y（批准）或 n（拒绝）", classes="hint"))
                return
            text = message.value.strip()
            message.input.clear()  # 回车即清空输入框，准备下一轮
            if not text:
                return  # 空回车忽略（IME 确认误触不退出；退出走 Ctrl+Q/Ctrl+C）
            if self._handle_focus_command(text):  # 焦点命令先于忙态拒绝（运行中亦可用）
                return
            if self._turn_busy:
                self._add(Static("处理中，请稍候（Ctrl+B 打断）", classes="hint"))
                return
            self._set_focus("")  # 普通输入 ⇒ 回主视图（回复不落进被隐藏的时间线）
            self._add(  # 用户输入回显：❯ 前缀行（Claude CLI 式，无气泡）
                Static(f"[{_ACCENT}]❯[/] {escape(text)}", classes="echo", markup=True)
            )
            self._turn_busy = True  # handler 内同步置位（与忙检同上下文，无竞态窗口）
            # 本轮执行进 worker：handler 即刻返回，消息泵保持可响应
            # （审批 y/n、Ctrl+B 打断等后续输入才能被分发——泵内 await 会死锁）
            if text.startswith("/task "):  # 任务命令：驱动编排器（不进普通对话）
                goal = text[len("/task ") :].strip()
                if goal:
                    self.run_worker(self._run_task_turn(goal))
                else:
                    self._turn_busy = False
                    self._add(Static("用法：/task <目标>", classes="hint"))
                return
            if self._handle_beast_command(text):  # 神兽斜杠入口（change 0137）
                return
            self.run_worker(self._run_turn(text))

        def _handle_beast_command(self, text: str) -> bool:
            """神兽斜杠入口 `/summon` `/recall`：命中即消费（用法错复位忙态，否则起 worker）。"""
            if text.split(maxsplit=1)[0] not in ("/summon", "/recall"):
                return False
            parsed = _parse_beast_command(text)
            if parsed is None:
                self._add(Static(_BEAST_USAGE, classes="hint"))
                self._turn_busy = False
            else:
                self.run_worker(self._run_beast_turn(*parsed))
            return True

        # ---- 神兽轮（/summon · /recall，change 0137 / 账本 E74）----

        async def _run_beast_turn(self, verb: str, target: str, beast_task: str) -> None:
            """神兽轮：状态行落时间线；召唤后结果**有才打印**（与 `summon` CLI 同口径）。"""
            self._spin_start("神兽就位中" if verb == "summon" else "召回中")
            try:
                summary = await api.beast_command(verb, target, task=beast_task)
                verb_cn = "已召唤神兽" if verb == "summon" else "已召回神兽"
                self._add(
                    Static(
                        f"{verb_cn} {summary['agent_id']}（状态 {summary['state']}）",
                        classes="hint",
                        markup=False,
                    )
                )
                if summary.get("has_result"):
                    outcome = "失败" if summary.get("failed") else "成功"
                    line = f"结果（{outcome}）：{summary.get('reply')}"
                    self._add(Static(line, classes="hint", markup=False))
            except UiError as err:
                line = _format_event(_error_event(err))
                if line:
                    self._add(Static(line, classes="fail", markup=False))
            finally:
                self._spin_stop()
                self._turn_busy = False

        # ---- 任务轮（/task）----

        async def _run_task_turn(self, goal: str) -> None:
            """任务轮：经 /task 驱动编排器，进度事件落时间线（单行提示+折叠块）。"""
            self._spin_start("任务执行中")
            try:
                async for event in api.run_task(session_id, goal):
                    self._add_task_widget(event)
            except UiError as err:
                line = _format_event(_error_event(err))
                if line:
                    self._add(Static(line, classes="fail", markup=False))
            finally:
                self._spin_stop()
                self._turn_busy = False

        def _add_task_widget(self, event: Event) -> None:  # noqa: PLR0911 — 一分支一事件
            """编排事件 → 时间线 widget：任务/波次浅灰单行，子任务折叠块，终态高亮。"""
            payload = event.payload
            if not isinstance(payload, dict):
                return
            data = cast(dict[str, Any], payload)
            kind = event.type.removeprefix("task.")
            if kind == "task_started":
                self._set_focus("")  # 新计划回主视图（否则计划头落进被隐藏的时间线）
                line = f"◍ 任务 {data.get('task_id')}：{data.get('goal', '')}"
                self._add(Static(line, classes="hint", markup=False))
                return
            if kind == "plan_ready":
                n = len(data.get("subtasks", []))
                line = f"▸ 拆解 {n} 个子任务 · 波次 {data.get('waves')}"
                self._add(Static(line, classes="hint", markup=False))
                return
            if kind == "wave_started":
                self._add(Static(f"▸ 波次 {data.get('wave')}", classes="hint", markup=False))
                return
            if kind == "subtask_started":
                self._open_subtask(str(data.get("subtask_id", "")), data)
                return
            if kind == "subtask_progress":
                self._progress_subtask(str(data.get("subtask_id", "")), data)
                return
            if kind == "subtask_completed":
                self._complete_subtask(str(data.get("subtask_id", "")), data)
                return
            if kind == "task_failed":
                line = f"✗ 任务失败 {data.get('code')}: {data.get('reason')}"
                self._add(Static(line, classes="fail", markup=False))
                return
            if kind == "task_finished":
                outcomes = data.get("outcomes", [])
                ok = sum(1 for o in outcomes if getattr(o, "ok", False))
                self._add(Static(f"✔ 任务完成（{ok}/{len(outcomes)} 子任务通过）", classes="ok"))

        def _add_action_widget(self, event: Event) -> None:
            """工具动作事件 → ⏺ 折叠块：友好名标题，完成落 ✓/✗+耗时，输出藏折叠区。"""
            payload = event.payload
            if not isinstance(payload, dict):
                return
            data = cast(dict[str, Any], payload)
            key = f"{data.get('round')}:{data.get('tool_id')}"
            kind = event.type.removeprefix("loop.action_")
            entry = self._actions.get(key)
            if kind == "started":
                detail = Static("", classes="hint", markup=False)  # 输出占位（completed 填充）
                box = Collapsible(
                    detail, title=f"⏺ {_tool_name(data.get('tool_id'))}", collapsed=True
                )
                self._add(box)
                self._actions[key] = (box, detail)
                return
            if entry is None:
                return
            box, detail = entry
            tool = _tool_name(data.get("tool_id"))
            if data.get("ok"):
                box.title = f"⏺ {tool} ✓ ({_fmt_ms(data.get('duration_ms'))})"
            else:
                box.title = f"⏺ {tool} ✗"
            detail.update(f"输出：{data.get('output', '')}")

        def _add_reasoning_widget(self, event: Event) -> None:
            """思考回显事件 → `▸ 思考` 折叠块（change `0145` / ADR-0137 / 账本 E60）。

            **缺省收起**（标题可见、正文藏折叠区）；同一轮的增量**归并到同一块**（增量追加，
            不逐段新建）。思考原文是**纯呈现层**：只在此处落块，不进转录 / 记忆 / 日志。
            """
            payload = event.payload
            if not isinstance(payload, dict):
                return
            text = str(cast(dict[str, Any], payload).get("text", ""))
            if not text:
                return
            entry = self._reasoning
            if entry is None:
                detail = Static(text, classes="hint", markup=False)
                box = Collapsible(detail, title="▸ 思考", collapsed=True)
                self._add(box)
                self._reasoning = (box, detail)
                return
            _, detail = entry
            detail.update(str(detail.render()) + text)

        def _open_subtask(self, sid: str, data: dict[str, Any]) -> None:
            """子任务开工：单行折叠块 + 验收详情（构造期入折叠区，收尾 update 补判定）。"""
            goal = str(data.get("goal", ""))
            detail = Static(
                f"验收：{data.get('acceptance') or '（无）'}",
                classes="hint",
                markup=False,
            )
            box = Collapsible(detail, title=f"▸ 子任务 {sid}  ⟳ {escape(goal)}", collapsed=True)
            self._add(box)
            self._open[sid] = (box, detail, goal)

        def _progress_subtask(self, sid: str, data: dict[str, Any]) -> None:
            """子任务里程碑：追加进展开区（工具类复用动作行口径：友好名 + 耗时，不暴露 id 与参数）。

            载荷已由编排层按内层类型白名单化（`_PROGRESS_FIELDS`）⇒ 表外类型静默丢弃、不落占位。
            """
            entry = self._open.get(sid)
            if entry is None:  # 无对应折叠块（未收到 subtask_started）⇒ 静默忽略
                return
            _, detail, _ = entry
            inner = data.get("data")
            line = format_action_event(str(data.get("event", "")), inner)
            if line is None:  # 轮次级里程碑（动作行不覆盖）
                if data.get("event") != "step_completed" or not isinstance(inner, dict):
                    return  # 表外/异常载荷不呈现（不落空行与占位）
                step = cast(dict[str, Any], inner)
                mark = "失败" if step.get("failed") else "完成"
                line = f"· 第 {step.get('round')} 轮{mark}"
            detail.update("\n".join([str(detail.render()), line]))
            if detail is self._focus_detail:  # 聚焦中 ⇒ 面板实时刷新
                self._render_panel()

        def _complete_subtask(self, sid: str, data: dict[str, Any]) -> None:
            """子任务收尾：标题落 ✓/✗，展开区 update 补判定与结果节选。"""
            entry = self._open.get(sid)
            if entry is None:
                return
            box, detail, goal = entry
            if data.get("skipped"):
                box.title = f"▸ 子任务 {sid}  ✓ 已完成（续跑跳过）"
                if detail is self._focus_detail:
                    self._render_panel()
                return
            mark = "✓" if data.get("ok") else "✗"
            box.title = f"▸ 子任务 {sid}  {mark} {escape(goal)}"
            lines = [str(detail.render()), f"判定：{data.get('reason', '')}"]
            reply = str(data.get("reply", "")).strip()
            if reply:
                lines.append(reply)
            detail.update("\n".join(lines))
            if detail is self._focus_detail:
                self._render_panel()

        # ---- 子 Agent 焦点视图（presentation-only：复用折叠块已渲染文本） ----

        def _set_focus(self, sid: str) -> bool:
            """切视图：`sid` 非空 ⇒ 聚焦该子任务，空 ⇒ 回主视图。返回是否命中。

            只切 `display`（时间线上 `_add`/热更新路径**无条件** `query_one("#timeline")`
            ⇒ 绝不 unmount）；`self._open` 跨任务不清空而 sid 逐任务复用 ⇒ 焦点绑定
            **widget 身份**（`_focus_box`/`_focus_detail`），非 sid 字符串。
            """
            if not sid:
                if not self._focus_sid:
                    return True  # 已在主视图 ⇒ 零 widget 抖动
                self._focus_sid = ""
                self._focus_box = None
                self._focus_detail = None
                self.query_one("#panel", Vertical).display = False
                self.query_one("#timeline", Vertical).display = True
                return True
            entry = self._open.get(sid)
            if entry is None:
                return False  # 无对应折叠块（未开工）⇒ 不切换（无「延迟聚焦」半开态）
            box, detail, _goal = entry
            self._focus_sid = sid
            self._focus_box = box
            self._focus_detail = detail
            self.query_one("#timeline", Vertical).display = False
            self.query_one("#panel", Vertical).display = True
            self._render_panel()
            return True

        def _render_panel(self) -> None:
            """面板重渲染：标题取折叠块标题（已转义口径），正文取详情已渲染文本。"""
            box, detail = self._focus_box, self._focus_detail
            if box is None or detail is None:
                return
            panel = self.query_one("#panel", Vertical)
            self.query_one("#panel-title", Static).update(
                f"[{_ACCENT}]◇[/] {box.title}  [dim]（/main 或 F2 返回主视图）[/]"
            )
            self.query_one("#panel-body", Static).update(str(detail.render()))
            panel.call_after_refresh(panel.scroll_end, animate=False)

        def _handle_focus_command(self, text: str) -> bool:
            """焦点命令（`/focus <sid>` / `/main`）拦截。返回是否已消费。

            成功切换**零时间线写入**（呈现层切换不改内容）；仅失败给提示。
            """
            if text == "/main":
                self._set_focus("")
                return True
            if text == "/focus":
                self._add(Static("用法：/focus <子任务标识>", classes="hint"))
                return True
            if text.startswith("/focus "):
                sid = text[len("/focus ") :].strip()
                if not sid:
                    self._add(Static("用法：/focus <子任务标识>", classes="hint"))
                    return True
                if not self._set_focus(sid):
                    self._add(Static(f"未找到子任务 {sid}（仍为主视图）", classes="hint"))
                return True
            return False

        def action_focus_main(self) -> None:
            """F2：返回主视图（无焦点时空操作）。"""
            self._set_focus("")

        # ---- 普通消息轮 ----

        async def _run_turn(self, text: str) -> None:
            """单轮执行：流式增量上 live、终态/错误落时间线；结束复位状态。"""
            self._spin_start("思考中")
            self._reasoning = None  # 思考块按**轮**归并（跨轮不复用同一折叠块）
            try:
                async for event in api.run_loop(session_id, text):
                    delta = _event_delta(event)
                    if delta is not None:
                        self._show_delta(delta)
                        continue
                    if event.type == "loop.reasoning":  # 思考回显（折叠块，缺省收起）
                        self._add_reasoning_widget(event)
                        continue
                    if event.type.startswith("loop.action_"):  # 工具动作行（折叠块）
                        self._add_action_widget(event)
                        continue
                    line = _format_event(event)
                    if line:
                        self._add(Static(line, classes="hint", markup=False))
            except UiError as err:
                line = _format_event(_error_event(err))
                if line:
                    self._add(Static(line, classes="fail", markup=False))
            finally:
                self._flush_live()
                self._spin_stop()
                self._turn_busy = False

    return ReplApp()


def run_repl(api: UIAPILayer, session_id: str = "") -> None:
    """启动 Textual 交互会话循环（阻塞；懒 import textual）。`session_id` 非空 ⇒ 续聊既有会话。"""
    build_app(api, session_id).run()
