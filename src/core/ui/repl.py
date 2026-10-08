"""Textual REPL 适配器（ui 接入层边界依赖）。

CLIBridge.connect() 落地为 Textual 交互会话循环；textual 仅此文件持有且懒 import
（ADR-0040 MAL 隔离），上层（cli_bridge / UIAPILayer）不依赖具体 TUI 框架。

对标 Claude CLI 的呈现层：
- core 主题（terracotta accent #d97757）+ 圆角输入框（focus 高亮）；
- 输入区/提示盒整体钉底（dock: bottom），时间线独占剩余高度（防 1fr 撑满）；
- 工作状态行 ✻ label… (Ns)（set_interval 轮换 glyph，无内置 Spinner 组件）；
- 回复流式增量直接落时间线尾部同一滚动流（连续滚动输出，视口跟随），每段即按
  Markdown 增量渲染（标题/代码高亮流式即所见），段边界固化 append-only，
  终态无整块替换、无重排跳变；增量**合帧节流**（入缓冲，40ms 合并渲染一次 ⇒
  渲染次数与分片速率解耦，避免每 delta 全量 re-parse/re-layout 的阶梯抖动）；
- 用户输入以 ❯ 前缀行回显；底部快捷键提示盒（F1 展开）；启动欢迎横幅；
- 任务/子任务进度走折叠块（单行提示 + 展开详情）。

对应接口：doc/03-interfaces/ui-interface.md §1（CLIBridge 交互会话面）。
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from core.diagnostics import (
    Deps,
    Report,
    collect_doctor,
    collect_status,
    render,
    render_config,
    render_mcp,
    render_notes,
    render_sessions,
    render_skills,
)

from .api import UIAPILayer
from .errors import UiError
from .models import Event

_ACCENT = "#d97757"  # core 主题 accent（Claude CLI terracotta）
_SPIN_GLYPHS = ["✻", "·", "•", "∘", "○"]  # 工作状态行轮换符号
_MS_PER_SECOND = 1000  # 耗时人类可读换算
_TAIL_FLUSH_S = 0.04  # 尾段合并节拍：SSE delta 只入缓冲，40ms 由 timer 合并渲染一次
_TAIL_SPLIT = 2000  # 流式尾段字符阈值：超过/行边界即固化（每 delta 重 wrap 有界）
_TAIL_FENCE_CAP = 8000  # 未闭合围栏内尾段硬上限：超此值强固化兜底，约束内存
_TAIL_TABLE_CAP = 8000  # 未闭合表格块内尾段硬上限：同围栏口径，约束内存
_TABLE_MIN_PIPES = 2  # 表格行最少竖线数（表格每行含分隔竖线；散文罕见）


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

_STEP_TAIL_LINES = 8  # 步骤块缩略态呈现的**末尾**行数（超出部分折叠，可点正文展开）

_TARGET_FIELDS = {  # tool_id → 标题目标摘要的**白名单结构性字段**（正文类参数永不取）
    "tools.file_read": "path",
    "tools.file_write": "path",
    "tools.file_patch": "path",
    "tools.web_fetch": "url",
    "tools.code_run": "script",
    "tools.gate_run": "gate",
    "tools.context_read": "pointer",
}
_MAX_TARGET_CHARS = 60  # 目标摘要上界（超长以省略号收尾）


def _tool_target(tool_id: object, args: object) -> str:
    """工具动作的**目标摘要**（单行 + 有界）；取不到 ⇒ `""`（标题只留友好名）。

    `args` 非 `Mapping` 时直接 `""` —— 事件面（`_args_excerpt`）对超长参数返回**节选字符串**，
    此处**不解析** repr（只吃结构化载荷），故大参数工具（Write/Patch）在此退化为无目标。
    """
    field = _TARGET_FIELDS.get(str(tool_id or ""))
    if not field or not isinstance(args, Mapping):
        return ""
    value = cast("Mapping[str, Any]", args).get(field)
    if not isinstance(value, str):
        return ""
    line = value.strip().split("\n", 1)[0].strip()
    if not line:
        return ""
    return line[:_MAX_TARGET_CHARS] + "…" if len(line) > _MAX_TARGET_CHARS else line


def _action_title(tool: str, target: str, *, ok: bool | None = None, ms: object = None) -> str:
    """工具步骤块标题：`⏺ <友好名>  <目标>`；完成落 `✓ (耗时)` / `✗`（**保留目标**）。"""
    base = f"⏺ {tool}" + (f"  {target}" if target else "")
    if ok is None:
        return base
    return f"{base} ✓ ({_fmt_ms(ms)})" if ok else f"{base} ✗"


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


@dataclass(frozen=True)
class _Command:
    """斜杠命令的**登记项**（单一真源）：浮层据此呈现，SHALL NOT 与分发各记一份。"""

    name: str  # 触发词（含前导斜杠）
    summary: str  # 浮层一行说明
    arg: str = ""  # 参数名（"" ⇒ 无参数；采纳后补出参数位）
    arg_source: str = (
        ""  # 参数候选来源键（"" ⇒ 不可枚举；"subtask" ⇒ 在途子任务；"session" ⇒ 会话）
    )
    handler: str = ""  # 处理器**方法名**（"" ⇒ 走既有专用分支；非空 ⇒ 只读命令直分发）


_COMMANDS: tuple[_Command, ...] = (
    _Command("/task", "启动编排任务", "目标"),
    _Command("/focus", "聚焦子任务视图", "子任务标识", "subtask"),
    _Command("/main", "返回主视图"),
    _Command("/summon", "召唤神兽执行任务", "神兽"),
    _Command("/recall", "召回神兽并取结果", "神兽"),
    _Command("/resume", "切换会话并还原其内容", "会话标识", "session"),
    # 只读命令族（change 0163 / ADR-0154）：真源即接线（`handler` 直分发，无参数面）
    _Command("/doctor", "自检诊断", handler="_show_doctor"),
    _Command("/status", "运行状态概览", handler="_show_status"),
    _Command("/sessions", "列出会话", handler="_show_sessions"),
    _Command("/config", "查看配置（密钥遮蔽）", handler="_show_config"),
    _Command("/mcp", "MCP 端点", handler="_show_mcp"),
    _Command("/skill", "技能目录", handler="_show_skill"),
    _Command("/notes", "笔记与常驻项", handler="_show_notes"),
)


def _lookup(name: str) -> _Command | None:
    """按命令名精确查真源（不在其中 ⇒ None）。"""
    return next((cmd for cmd in _COMMANDS if cmd.name == name), None)


@dataclass(frozen=True)
class _Candidate:
    """浮层候选项：`fill` 为采纳后写入输入框的整串（**不含**补位空格）。"""

    key: str  # OptionList 选项 id（唯一）
    label: str  # 浮层显示行
    fill: str  # 采纳后填入输入框的文本
    arg_next: bool = False  # 采纳后补一个空格进入二级（仅带参数命令）


def _palette_options(
    value: str,
    *,
    subtask_ids: Sequence[str] = (),
    sessions: Sequence[tuple[str, str]] = (),
) -> list[_Candidate]:
    """当前输入下的浮层候选（空列表 ⇒ 不呈现浮层）。

    一级：`/` 起始且**尚未出现空格** ⇒ 按前缀筛真源命令；
    二级：`<命令> <参数>`（参数内无空格 + 该命令参数**可枚举**）⇒ 列该命令 `arg_source`
    对应的既有候选（`subtask` ⇒ 在途子任务标识；`session` ⇒ 已登记会话）；
    其余（非 `/` 起始、未知命令、带参命令已进参数位、参数含空格）⇒ 不呈现。
    """
    if not value.startswith("/"):
        return []
    head, sep, arg = value.partition(" ")
    if not sep:  # 一级：命令名（尚未出现空格）
        return [
            _Candidate(
                key=f"cmd:{cmd.name}",
                label=f"{cmd.name} <{cmd.arg}> {cmd.summary}"
                if cmd.arg
                else f"{cmd.name} {cmd.summary}",
                fill=cmd.name,
                arg_next=bool(cmd.arg),
            )
            for cmd in _COMMANDS
            if cmd.name.startswith(value)
        ]
    cmd = _lookup(head)
    if cmd is None or not cmd.arg_source or " " in arg:
        return []
    if cmd.arg_source == "session":
        # 会话候选按**显示行前缀**（大小写不敏感）或**标识前缀**收窄（标题可读、标识可粘）
        pool = [
            (sid, label)
            for sid, label in sessions
            if not arg or label.lower().startswith(arg.lower()) or sid.startswith(arg)
        ]
    else:  # "subtask"：既有在途子任务标识（参数源与命令一一对应，见真源 `arg_source`）
        pool = [(sid, sid) for sid in subtask_ids if sid.startswith(arg)]
    return [_Candidate(key=f"arg:{sid}", label=label, fill=f"{head} {sid}") for sid, label in pool]


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
    from textual import events  # noqa: PLC0415 — MAL 懒 import
    from textual.app import App, ComposeResult  # noqa: PLC0415 — MAL 懒 import
    from textual.containers import Horizontal, Vertical  # noqa: PLC0415 — MAL 懒 import
    from textual.suggester import Suggester  # noqa: PLC0415 — MAL 懒 import
    from textual.theme import Theme  # noqa: PLC0415 — MAL 懒 import
    from textual.timer import Timer  # noqa: PLC0415 — MAL 懒 import
    from textual.widget import Widget  # noqa: PLC0415 — MAL 懒 import
    from textual.widgets import (  # noqa: PLC0415 — MAL 懒 import
        Collapsible,
        Input,
        Markdown,
        OptionList,
        Static,
    )
    from textual.widgets.option_list import Option  # noqa: PLC0415 — MAL 懒 import

    approval = api.approval  # 审批通道（None 表示非交互入口，confirm 门 fail-closed）
    core_theme = Theme(name="core", primary=_ACCENT, accent=_ACCENT, secondary=_ACCENT, dark=True)

    class _PaletteList(OptionList, can_focus=False):
        """命令浮层：**不可聚焦**（`Tab` 不得把焦点从输入框抢走），仅由代码驱动高亮。"""

    class _StepBlock(Collapsible):
        """步骤块（思考 / 工具动作共用）：缺省**缩略**（末尾 `_STEP_TAIL_LINES` 行）。

        三态 = `collapsed`（Textual 折叠，点标题切）× `_full`（窗口，点正文切）：
        收起 / 缩略 / 全文。行缓冲 append-only（末元素是未完成行）⇒ 消原全文重拼的 O(n²)。
        """

        def __init__(self, title: str) -> None:
            self._lines: list[str] = [""]
            self._full = False
            self._body = Static("", classes="step-body", markup=False)
            self._more = Static("", classes="step-more")
            super().__init__(self._body, self._more, title=title, collapsed=False)

        def feed(self, text: str) -> None:
            """增量追加片段（只追加、不重拼 ⇒ 长流实时可见）。"""
            parts = text.split("\n")
            self._lines[-1] += parts[0]
            self._lines.extend(parts[1:])
            self._render_body()

        def set_text(self, text: str) -> None:
            """一次性成文（工具输出：整体替换）。"""
            self._lines = text.split("\n")
            self._render_body()

        def _render_body(self) -> None:
            """切窗口 → 加 `└` 肘线 → 落剩余提示（唯一拼文本处）。"""
            total = len(self._lines)
            lines = self._lines if self._full else self._lines[-_STEP_TAIL_LINES:]
            body = "\n".join(("└ " if i == 0 else "  ") + ln for i, ln in enumerate(lines))
            self._body.update(body)
            hidden = 0 if self._full else total - len(lines)
            if hidden:
                self._more.update(f"⋯ 还有 {hidden} 行 · 点击展开全文")
            elif self._full and total > _STEP_TAIL_LINES:
                self._more.update("⋯ 点击正文收起")
            else:
                self._more.update("")

        def on_click(self, event: events.Click) -> None:
            """点**正文**：缩略 ⇄ 全文（收起态或无剩余行时空操作 —— 不出现「点了没变化」）。"""
            if self.collapsed or len(self._lines) <= _STEP_TAIL_LINES:
                return
            self._full = not self._full
            self._render_body()

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
.step-body {  /* 步骤块正文（思考 / 工具输出）：**确定宽度** ⇒ 超宽行折行而非被祖先裁掉 */
    color: $text-muted;
    width: 1fr;
}
.step-more {  /* 步骤块剩余行提示：更浅一档（不抢正文） */
    color: $text-disabled;
    width: 1fr;
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
MarkdownFence {  /* 代码块：默认 `black 10%` 在深色底上合成近同色（对比度≈1.02，用户实测不可辨）
                    ⇒ 换为不透明中性灰，块边界一眼可辨；token 高亮仍为亮色，深灰底上可读
                    （change 0158 / ADR-0150） */
    background: $surface-lighten-3;
}
#palette {  /* 斜杠命令浮层：默认隐藏，输入 `/` 时经 `display` 翻转呈现（沿 #panel 惯用法）
               —— 不引入 Screen/layer；不可聚焦（见 _PaletteList）（change 0159 / ADR-0151） */
    display: none;
    height: auto;
    max-height: 8;
    border: round $panel;
    margin: 0 1;
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

        def __init__(self, session_id: str, history: list[dict[str, Any]]) -> None:
            super().__init__()
            self._session_id = session_id  # 当前会话（`/resume` 运行中可切；原为闭包变量）
            self._history = history  # 启动续聊的既有转录（on_mount 铺入后不再用）
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
            self._actions: dict[str, tuple[_StepBlock, str]] = {}  # round:tool→(块, 目标摘要)
            self._reasoning: _StepBlock | None = None  # 本轮思考块（同轮归并）
            self._spin_timer: Timer | None = None  # 工作状态行驱动
            self._tail_timer: Timer | None = None  # 尾段合并渲染驱动（懒启动，同 spinner）
            self._tail_dirty = False  # 有未渲染增量（下一次 flush 合并渲染一次）
            self._flushing = False  # 重入闸：_flush_tail 内部经 _add 挂尾块
            self._spin_t0 = 0.0
            self._spin_idx = 0
            self._spin_label = ""
            self._hints_on = False
            self._palette_open = False  # 浮层呈现中（按键接管与采纳的闸）
            self._palette_cands: list[_Candidate] = []  # 当前候选（采纳时按高亮项取）

        def compose(self) -> ComposeResult:
            yield Vertical(id="timeline")
            with Vertical(id="panel"):  # 子 Agent 焦点视图（初始隐藏，见 on_mount）
                yield Static(id="panel-title")
                yield Static("", id="panel-body", classes="hint", markup=False)
            yield Static(id="spinner")
            yield _PaletteList(id="palette")  # 斜杠命令浮层（CSS 初始 display:none）
            with Vertical(id="footer"):  # 输入区+提示盒钉底，时间线独占剩余空间
                with Horizontal(id="input-box"):
                    yield Static("❯ ", id="prompt")
                    yield Input(
                        placeholder="发送消息，或 /task <目标> 启动编排任务",
                        id="input",
                        suggester=_PaletteSuggester(self._candidates),  # 幽灵补全（与浮层同源）
                    )
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
                self._replay_history(self._session_id, history)

        def _replay_history(self, sid: str, items: list[dict[str, Any]]) -> None:
            """把某会话的既有转录铺入时间线（启动续聊与 `/resume` 切换**同一**路径 ⇒ 格式一致）。"""
            self._add(Static(f"↻ 续接会话 {sid}（{len(items)} 条历史已载入）", classes="ok"))
            for item in items:
                if item.get("role") == "user":
                    content = escape(str(item.get("content", "")))
                    self._add(Static(f"[{_ACCENT}]❯[/] {content}", classes="echo", markup=True))
                else:
                    # agent 回复按 **Markdown** 铺入（与实时流式路径**同一**格式 ⇒ 代码围栏
                    # 成代码块、表格成表格），SHALL NOT 退化为逐行明文（change 0157 / ADR-0149）
                    self._add(Markdown(str(item.get("content", ""))))

        # ---- 时间线 ----

        def _add(self, widget: Widget) -> None:
            """时间线追加 widget 并滚到底（mount 不等待，消息泵不被阻塞）。

            挂**非尾** widget 前先提交挂起尾段（合帧节流下 delta 尚未渲染）：
            保时序（挂起文本在动作行/思考块/审批提示/打断提示**之上**），
            覆盖 barge-in / 审批中途挂件等非 delta 事件路径。重入安全。"""
            if not self._flushing:  # 防重入：_flush_tail 内部经 _add 挂尾块
                self._flush_tail()
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
            self._close_palette()  # 审批期不呈现浮层（y/n 决断输入不被遮蔽）
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
            """流式增量**入缓冲（不即时渲染）**：40ms 合拍由 timer 合并热更新一次，
            避免每 delta 全量 re-parse/re-layout 的阶梯抖动；终态/边界分支逻辑不变。"""
            self._live_buf.append(delta)
            self._tail_buf.append(delta)
            self._tail_dirty = True
            if self._tail_timer is None:  # 懒启动（同 spinner）：空闲不空转
                self._tail_timer = self.set_interval(_TAIL_FLUSH_S, self._flush_tail)

        def _flush_tail(self) -> None:
            """合并渲染：把挂起尾段按 fence/table/split 分支收口一次（timer 或事件边界驱动）。

            重入安全（`_flushing`）+ 幂等（`_tail_dirty`）：`_add` 可在挂非尾 widget 前
            无条件调用。围栏未闭合时热更新（流式可见）；**表格未闭合时延后**（不绘制中间态，
            闭合或超硬上限后一次整块成型）；常规路径按行边界/阈值固化。"""
            if not self._tail_dirty or self._flushing:
                return
            self._flushing = True
            try:
                self._tail_dirty = False
                text = "".join(self._tail_buf)
                if self._in_open_fence(text):
                    # 围栏未闭合：不按行/常规阈值固化（避免大代码块被拦腰截断），
                    # 仅超硬上限时兜底固化，约束内存与重 wrap 代价
                    if len(text) >= _TAIL_FENCE_CAP:
                        self._freeze_tail(text)
                    else:
                        self._touch_tail(text)
                    return
                if self._in_open_table(text):
                    # 表格未闭合：表格须整块（表头 + 分隔行 + 数据行）方能解析 ⇒
                    # 延后渲染（不逐行重排、列宽只算一次），超硬上限才兜底固化
                    if len(text) >= _TAIL_TABLE_CAP:
                        self._freeze_tail(text)
                    return
                if len(text) >= _TAIL_SPLIT or text.endswith("\n"):
                    self._freeze_tail(text)
                else:
                    self._touch_tail(text)
            finally:
                self._flushing = False

        @staticmethod
        def _in_open_fence(text: str) -> bool:
            """尾段是否处于未闭合代码围栏内（行首 ``` / ~~~ 数量为奇数）。"""
            fences = sum(1 for line in text.split("\n") if line.lstrip().startswith(("```", "~~~")))
            return fences % 2 == 1

        @staticmethod
        def _in_open_table(text: str) -> bool:
            """尾段是否处于未闭合 Markdown 表格块内（表格须整块解析：表头行 + 分隔行 +
            数据行，中间无空行）⇒ 与围栏同理延后固化。判据：当前块（自尾向前的连续非空行，
            行终止用的单个尾 `\\n` 不算空行）**每行都含 ≥ `_TABLE_MIN_PIPES` 个 `|`**
            （表格每行含分隔竖线，散文罕见）。围栏由 `_in_open_fence` 先判，故围栏内
            `|` 不会走到此。"""
            body = text[:-1] if text.endswith("\n") else text
            block: list[str] = []
            for line in reversed(body.split("\n")):
                if not line.strip():
                    break
                block.append(line)
            return bool(block) and all(ln.count("|") >= _TABLE_MIN_PIPES for ln in block)

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
            """流式终态：停合帧节拍 + 尾段固化为最后一块 Markdown，已固化块原样保留。
            覆盖「已热更新的尾块」与「仅缓冲未渲染的尾段」（含被延后的未闭合表格）⇒
            回复结束（含异常/中断）**不丢字**。全程同格式渲染，无终态整块替换、无重排跳变。"""
            if self._tail_timer is not None:
                self._tail_timer.stop()  # 收尾停表（不再有合帧触发）
                self._tail_timer = None
            self._tail_dirty = False  # 直接走下方 _freeze_tail，不再经 _flush_tail（免双重渲染）
            if self._tail_buf:
                self._freeze_tail("".join(self._tail_buf))
            self._last_reply = "".join(self._live_buf)
            self._tail_widget = None
            self._tail_buf = []
            self._live_buf = []

        # ---- 输入分发 ----

        def on_input_submitted(self, message: Input.Submitted) -> None:  # noqa: C901, PLR0911, PLR0912 — 一分支一返回
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
            if self._palette_open and self._accept_palette_selection():
                return  # 浮层采纳：只补全输入框，不提交（下次回车才走既有分发链）
            text = message.value.strip()
            message.input.clear()  # 回车即清空输入框，准备下一轮
            if not text:
                return  # 空回车忽略（IME 确认误触不退出；退出走 Ctrl+Q/Ctrl+C）
            if self._handle_focus_command(text):  # 焦点命令先于忙态拒绝（运行中亦可用）
                return
            if self._turn_busy:
                self._add(Static("处理中，请稍候（Ctrl+B 打断）", classes="hint"))
                return
            if self._handle_resume_command(text):  # 会话切换（忙态后：与在途轮次互斥）
                return
            if self._dispatch_registered(text):  # 真源登记的只读命令（忙态后：同 /resume 一侧）
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

        # ---- 斜杠命令浮层与补全（change 0159 / ADR-0151） ----

        def _candidates(self, value: str) -> list[_Candidate]:
            """当前输入的浮层候选：参数候选取**既有**面（子任务标识 / 会话清单），零新增数据源。

            会话面只在输入确实落到**需要它**的命令的参数位时才取（按真源登记项的
            `arg_source` 判 —— 不按命令名字面量），避免每次按键都读会话面。
            """
            head, sep, _arg = value.partition(" ")
            cmd = _lookup(head) if sep else None
            sessions: Sequence[tuple[str, str]] = (
                self._session_candidates()
                if cmd is not None and cmd.arg_source == "session"
                else ()
            )
            return _palette_options(value, subtask_ids=tuple(self._open), sessions=sessions)

        def _session_candidates(self) -> tuple[tuple[str, str], ...]:
            """会话候选 `(标识, 显示行)`：取自**既有** `UIAPILayer.list_sessions()`。"""
            out: list[tuple[str, str]] = []
            for entry in api.list_sessions():
                sid = str(entry.get("session_id", ""))
                if not sid:
                    continue
                title = str(entry.get("title") or "")
                stamp = float(cast(float, entry.get("updated_at", 0.0)) or 0.0)
                when = time.strftime("%m-%d %H:%M", time.localtime(stamp)) if stamp else "—"
                out.append((sid, f"{title or '(无标题)'} · {sid} · {when}"))
            return tuple(out)

        def _refresh_palette(self, value: str) -> None:
            """按当前输入开合浮层：有候选且**无待决审批** ⇒ 呈现，否则收起。"""
            pending = self._approval_future
            if pending is not None and not pending.done():
                self._close_palette()  # 审批期不呈现（y/n 决断输入不被遮蔽）
                return
            cands = self._candidates(value)
            if not cands:
                self._close_palette()
                return
            palette = self.query_one("#palette", OptionList)
            palette.set_options([Option(c.label, id=c.key) for c in cands])
            palette.highlighted = 0
            palette.display = True
            self._palette_open = True
            self._palette_cands = cands

        def _close_palette(self) -> None:
            """收起浮层（幂等）。"""
            self._palette_open = False
            self._palette_cands = []
            self.query_one("#palette", OptionList).display = False

        def _accept_palette_selection(self) -> bool:
            """采纳浮层高亮项：把候选文本写回输入框并返回 True（**不提交**）。

            高亮项**不构成对当前输入的前缀延伸**时返回 False（无高亮 / 文本相同 / 非前缀）
            ⇒ 回车按**既有**分发链继续 —— 完整命令输入（如 `/main`）因此**逐字不变**地走原路径。
            """
            if not self._palette_open:
                return False
            option = self.query_one("#palette", OptionList).highlighted_option
            if option is None or option.id is None:
                return False
            cand = next((c for c in self._palette_cands if c.key == option.id), None)
            if cand is None:
                return False
            inp = self.query_one("#input", Input)
            if cand.fill == inp.value or not cand.fill.startswith(inp.value):
                return False
            inp.value = cand.fill + (" " if cand.arg_next else "")
            return True

        def on_input_changed(self, message: Input.Changed) -> None:
            """输入变化 ⇒ 重筛浮层（`Input.Changed` 冒泡至 App）。"""
            self._refresh_palette(message.value)

        def on_key(self, event: events.Key) -> None:
            """浮层呈现时接管 `↑`/`↓`/`Tab`/`Esc`；未呈现 ⇒ 一律放行（既有按键逐字不变）。

            实测（承重，勿凭直觉）：`Tab` **不是空键** —— App 默认「焦点后移」会把它从输入框
            带走，且声明 `BINDINGS` **无效**（默认焦点后移仍胜出），只有 `on_key` +
            `prevent_default` 才扣得下；故浮层另以 `can_focus=False`（`_PaletteList`）作双保险。
            `Enter` **不在此处理**（与 `Input.Submitted` 同触，两处都写会重复执行），采纳落在
            `on_input_submitted`。
            """
            if not self._palette_open:
                return
            if event.key in ("up", "down"):
                palette = self.query_one("#palette", OptionList)
                if event.key == "up":
                    palette.action_cursor_up()
                else:
                    palette.action_cursor_down()
            elif event.key == "tab":
                self._accept_palette_selection()
            elif event.key == "escape":
                self._close_palette()
            else:
                return  # Enter 等交回既有路径（采纳见 on_input_submitted）
            event.stop()
            event.prevent_default()

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
                async for event in api.run_task(self._session_id, goal):
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
            """工具动作事件 → ⏺ 步骤块：友好名 + 目标摘要标题，完成落 ✓/✗+耗时，输出走缩略正文。"""
            payload = event.payload
            if not isinstance(payload, dict):
                return
            data = cast(dict[str, Any], payload)
            key = f"{data.get('round')}:{data.get('tool_id')}"
            kind = event.type.removeprefix("loop.action_")
            entry = self._actions.get(key)
            if kind == "started":
                target = _tool_target(data.get("tool_id"), data.get("args"))
                box = _StepBlock(_action_title(_tool_name(data.get("tool_id")), target))
                self._add(box)
                self._actions[key] = (box, target)
                return
            if entry is None:
                return
            box, target = entry
            box.title = _action_title(
                _tool_name(data.get("tool_id")),
                target,  # 完成态**保留**目标（只加 ✓/✗ 与耗时）
                ok=bool(data.get("ok")),
                ms=data.get("duration_ms"),
            )
            box.set_text(str(data.get("output", "")))  # 正文已在 `└` 肘线下，不再加「输出：」前缀

        def _add_reasoning_widget(self, event: Event) -> None:
            """思考回显事件 → `▸ 思考` 步骤块（change `0145` / ADR-0137 / 账本 E60）。

            **缺省缩略**（缺省展开、正文只呈现末尾 `_STEP_TAIL_LINES` 行，点正文展开全文 / 点标题
            收起 —— 见 change `0169` / ADR-0160）；同一轮的增量**归并到同一块**（append-only 追加，
            不逐段新建、不全文重拼）。思考原文是**纯呈现层**：只在此处落块，不进转录 / 记忆 / 日志。
            """
            payload = event.payload
            if not isinstance(payload, dict):
                return
            text = str(cast(dict[str, Any], payload).get("text", ""))
            if not text:
                return
            entry = self._reasoning
            if entry is None:
                box = _StepBlock("▸ 思考")
                self._add(box)
                box.feed(text)
                self._reasoning = box
                return
            entry.feed(text)

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

        # ---- 会话切换（`/resume`，change 0160 / ADR-0152） ----

        def _handle_resume_command(self, text: str) -> bool:
            """`/resume [<会话标识>]` 拦截（承「忙态后」调用 ⇒ 与在途轮次互斥）。"""
            if text == "/resume" or text.startswith("/resume "):
                sid = text[len("/resume") :].strip()
                if not sid:
                    self._add(Static("用法：/resume <会话标识>", classes="hint"))
                else:
                    self._switch_session(sid)
                return True
            return False

        def _switch_session(self, sid: str) -> bool:
            """切换到既有会话：清时间线 → 铺入目标转录 → 复位呈现态与会话标识。

            **先验证、后落地**（fail-closed）：`session_messages` 对未登记标识拒绝 ⇒ 当前会话的
            时间线 / 标识 / 呈现态**逐字不变**，仅落一行错误（不留下「空时间线 + 旧会话」态）。
            """
            try:
                items = api.session_messages(sid)  # 未登记 ⇒ UiError（先于任何状态改动）
            except UiError as err:
                line = _format_event(_error_event(err))
                if line:
                    self._add(Static(line, classes="fail", markup=False))
                return False
            self._close_palette()
            self.query_one("#timeline", Vertical).remove_children()
            self._set_focus("")  # 焦点块已随时间线销毁 ⇒ 先回主视图再清句柄
            self._reset_turn_state()
            self._session_id = sid
            self._replay_history(sid, list(items))
            return True

        def _reset_turn_state(self) -> None:
            """清空**跨会话无意义**的呈现态（旧内容已随时间线销毁 ⇒ 句柄不得悬挂）。"""
            self._open.clear()
            self._actions.clear()
            self._reasoning = None
            self._live_buf = []
            self._tail_buf = []
            self._tail_widget = None
            self._last_reply = ""

        # ---- 只读命令族（`/doctor` `/status` `/sessions` `/config` `/mcp` `/skill` `/notes`） ----
        #
        # change 0163 / ADR-0154：命令名 → 处理器的对应关系取自真源（`_Command.handler`），
        # 本段**只做取数与呈现**；检查逻辑全部在 CLI 侧**同一**只读诊断源（`core.diagnostics`）里。

        def _dispatch_registered(self, text: str) -> bool:
            """真源登记的**只读**命令分发（`handler` 非空者）。返回是否已消费。

            未登记 / 无 `handler` ⇒ 返回 False（既有分支链与次序**逐字不动**）；只读命令**无参数面**
            ⇒ 带参数只提示、不执行。
            """
            head, _, arg = text.partition(" ")
            cmd = _lookup(head)
            if cmd is None or not cmd.handler:
                return False
            if arg.strip():
                self._add(Static(f"{cmd.name} 不接受参数", classes="hint"))
                return True
            getattr(self, cmd.handler)()
            return True

        def _readonly_report(self, build: Callable[[Deps], Report]) -> None:
            """取数 + 落结果块；诊断源未接线 ⇒ 一行提示（不崩、不进对话）。"""
            deps = api.diagnostics()
            if deps is None:
                self._add(Static("诊断源未接线（该只读命令不可用）", classes="hint"))
                return
            self._add(Static("\n".join(render(build(deps))), classes="hint", markup=False))

        def _show_doctor(self) -> None:
            """`/doctor`：逐项自检（与 CLI `doctor` 同源）。"""
            self._readonly_report(collect_doctor)

        def _show_status(self) -> None:
            """`/status`：运行状态概览（与 CLI `status` 同源）。"""
            self._readonly_report(collect_status)

        def _show_sessions(self) -> None:
            """`/sessions`：会话注册表清单（与 `/resume` 二级候选**同源**；只列不切）。"""
            self._readonly_report(render_sessions)

        def _show_config(self) -> None:
            """`/config`：配置视图（密钥**只出引用名 + 布尔结论**）。"""
            self._readonly_report(render_config)

        def _show_mcp(self) -> None:
            """`/mcp`：MCP 端点（**不出** `args` —— 可能含 `--token`）。"""
            self._readonly_report(render_mcp)

        def _show_skill(self) -> None:
            """`/skill`：技能目录（市场 + 技能库）。"""
            self._readonly_report(render_skills)

        def _show_notes(self) -> None:
            """`/notes`：笔记与常驻项。"""
            self._readonly_report(render_notes)

        # ---- 普通消息轮 ----

        async def _run_turn(self, text: str) -> None:
            """单轮执行：流式增量上 live、终态/错误落时间线；结束复位状态。"""
            self._spin_start("思考中")
            self._reasoning = None  # 思考块按**轮**归并（跨轮不复用同一折叠块）
            try:
                async for event in api.run_loop(self._session_id, text):
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

    class _PaletteSuggester(Suggester):
        """内联幽灵补全：与浮层候选**同源**（复用同一候选取口），`→` 由 `Input` 原生采纳。

        语料随上下文变化（子任务标识会增长）⇒ 关缓存；候选区分大小写（命令名为小写，
        默认的 casefold 会与 `Input` 按长度切取的幽灵文本错位）。
        """

        def __init__(self, candidates: Callable[[str], list[_Candidate]]) -> None:
            super().__init__(use_cache=False, case_sensitive=True)
            self._candidates_of = candidates

        async def get_suggestion(self, value: str) -> str | None:
            for cand in self._candidates_of(value):
                if cand.fill != value and cand.fill.startswith(value):
                    return cand.fill
            return None

    return ReplApp(session_id, history)


def run_repl(api: UIAPILayer, session_id: str = "") -> None:
    """启动 Textual 交互会话循环（阻塞；懒 import textual）。`session_id` 非空 ⇒ 续聊既有会话。"""
    build_app(api, session_id).run()
