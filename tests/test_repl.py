"""repl 单元测试（对齐契约红线：多轮上下文 / 空输入/EOF 退出 / barge-in 打断 / 错误降级）。"""

from __future__ import annotations

import asyncio

import pytest

from core.configuration.models import LLMConfig
from core.loop import LoopEvent, LoopResult
from core.memory import TranscriptStore
from core.ui import Event, UIAPILayer, UiError, UiErrorCode
from core.ui.repl import (
    _event_delta,
    _format_event,
    _palette_options,
    _parse_beast_command,
    barge_in_event,
    build_app,
    format_task_event,
    repl_loop,
)


class RecordingLoop:
    """记录每次输入并回显的 loop 替身（区分多轮）。"""

    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def astream(self, user_input: str, *, session_id: str = ""):
        self.inputs.append(user_input)
        yield LoopEvent("loop_finished", {"reply": f"echo:{user_input}"})


def _llm(key: str = "${OPENAI_API_KEY}") -> LLMConfig:
    return LLMConfig(provider="openai", model="gpt-4o", endpoint="https://x", api_key_ref=key)


async def _drive(
    api: UIAPILayer,
    session_id: str,
    lines: list[str | None],
) -> list[Event]:
    """以给定输入行序列驱动 repl_loop，返回写入的事件。"""
    written: list[Event] = []
    it = iter(lines)

    async def read() -> str | None:
        return next(it)

    async def write(event: Event) -> None:
        written.append(event)

    await repl_loop(api, session_id, read=read, write=write)
    return written


def test_repl_loop_multi_turn_reuses_session() -> None:
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())
    session_id = api.create_session("cli")

    written = asyncio.run(_drive(api, session_id, ["hello", "world", None]))

    assert loop.inputs == ["hello", "world"]
    assert [e.type for e in written] == ["loop.result", "loop.result"]
    assert written[0].payload["reply"] == "echo:hello"
    assert written[1].payload["reply"] == "echo:world"


def test_repl_loop_empty_input_exits() -> None:
    api = UIAPILayer(loop=RecordingLoop())
    api.set_llm_config(_llm())
    session_id = api.create_session("cli")

    written = asyncio.run(_drive(api, session_id, ["", "should-not-run"]))

    assert written == []


def test_repl_loop_eof_exits() -> None:
    api = UIAPILayer(loop=RecordingLoop())
    api.set_llm_config(_llm())
    session_id = api.create_session("cli")

    written = asyncio.run(_drive(api, session_id, [None]))

    assert written == []


def test_repl_loop_error_degrades_to_event() -> None:
    api = UIAPILayer(loop=RecordingLoop())  # 未配 LLM key
    session_id = api.create_session("cli")

    written = asyncio.run(_drive(api, session_id, ["hi", None]))

    assert [e.type for e in written] == ["error"]
    assert written[0].payload["code"] == UiErrorCode.UI_LLM_KEY_UNSET.value


def test_repl_barge_in_degrades_gracefully() -> None:
    event = barge_in_event(UIAPILayer())

    assert event.type == "error"
    assert event.payload["code"] == UiErrorCode.UI_BARGEIN.value


def test_format_event_strips_scaffolding() -> None:
    """REPL 只回显回复文本与错误，剥离 session/trace/round/LoopResult 脚手架。"""
    assert _format_event(Event("session.created", {"session_id": "s", "trace_id": "t"})) is None
    assert _format_event(Event("loop.action", {"round": 1, "failed": False})) is None
    assert _format_event(Event("loop.delta", {"text": "你好"})) == "你好"
    assert _format_event(Event("loop.result", LoopResult(reply="hi", trace_id="t"))) is None
    assert _format_event(Event("loop.error", {"reason": "LOOP_LIMIT_EXCEEDED"})) == (
        "[loop.error] LOOP_LIMIT_EXCEEDED"
    )
    assert _format_event(Event("error", {"code": "X", "message": "m"})) == "[X] m"


def test_event_delta_only_accepts_dedicated_type() -> None:
    """增量分流**只认类型**（change `0132` / ADR-0125 / 账本 E65）。

    增量与终态不再共型：`loop.delta` 的 dict 载荷取 `text`；`loop.result` 一律不是增量
    （即便载荷恰为 dict —— 该共型正是 Web 渲染破碎的根因）。
    """
    assert _event_delta(Event("loop.delta", {"text": "增量"})) == "增量"
    assert _event_delta(Event("loop.delta", {"text": ""})) is None
    assert _event_delta(Event("loop.delta", LoopResult(reply="x", trace_id="t"))) is None
    assert _event_delta(Event("loop.result", {"text": "旧共型"})) is None
    assert _event_delta(Event("loop.action", {"round": 1})) is None


def test_textual_app_headless_smoke() -> None:
    """真实 Textual 接线冒烟：headless 构建 + 输入驱动 run_loop + barge-in 键。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> None:
        async with app.run_test() as pilot:
            await pilot.press("h", "i", "enter")
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.pause()

    asyncio.run(drive())
    assert loop.inputs == ["hi"]


def test_input_clears_after_submit() -> None:
    """回车后输入框立即清空（准备下一轮）。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> None:
        async with app.run_test() as pilot:
            await pilot.press("h", "i")
            await pilot.pause()
            assert app.query_one("#input").value == "hi"
            await pilot.press("enter")
            await pilot.pause()
            assert app.query_one("#input").value == ""

    asyncio.run(drive())
    assert loop.inputs == ["hi"]


# ---- TUI 任务入口（/task 命令驱动编排器，进度事件流式呈现） ----


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


class _TaskOrchestrator:
    """编排器桩：回放进度事件并记录目标。"""

    def __init__(self, events: list[tuple[str, dict]]) -> None:
        self._events = events
        self.goals: list[str] = []

    async def astream(self, task_id: str, goal: str, **kwargs: object):
        self.goals.append(goal)
        for kind, payload in self._events:
            yield LoopEvent(kind, payload)


def test_format_task_event_renders_progress_lines() -> None:
    assert format_task_event("task_started", {"task_id": "t1", "goal": "复合目标"}) == (
        "[task] 任务 t1：复合目标"
    )
    assert format_task_event("subtask_completed", {"subtask_id": "1", "ok": True}) == (
        "[子任务 1] ✓"
    )
    assert (
        format_task_event("subtask_completed", {"subtask_id": "2", "ok": False, "reason": "未达标"})
        == "[子任务 2] ✗ — 未达标"
    )
    assert format_task_event("unknown_kind", {"x": 1}) is None


def test_format_event_maps_task_prefixed_events() -> None:
    assert _format_event(Event("task.task_started", {"task_id": "t1", "goal": "g"})) == (
        "[task] 任务 t1：g"
    )


def test_task_command_drives_orchestrator_not_loop() -> None:
    """/task 命令驱动编排器（不进普通对话），进度事件落日志，结束后忙态复位。"""
    orch = _TaskOrchestrator(
        [
            ("task_started", {"task_id": "t1", "goal": "build it"}),
            ("task_finished", {"outcomes": []}),
        ]
    )
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop, orchestrator=orch)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> str:
        async with app.run_test() as pilot:
            for ch in "/task build it":
                await pilot.press(ch)
            await pilot.press("enter")
            for _ in range(50):  # 等 worker 跑完编排桩（事件即时产出）
                await pilot.pause()
                if orch.goals:
                    break
            for _ in range(5):
                await pilot.pause()
            await pilot.press("h", "i", "enter")  # 忙态复位后普通消息可继续
            for _ in range(10):
                await pilot.pause()
            return _timeline_text(app)

    text = asyncio.run(drive())
    assert orch.goals == ["build it"]
    assert loop.inputs == ["hi"]  # /task 不进普通对话；结束后复位可继续
    assert "◍ 任务 t1：build it" in text
    assert "任务完成" in text  # task_finished 终态单行（✔ 任务完成…）


def test_task_command_without_goal_shows_usage() -> None:
    orch = _TaskOrchestrator([])
    api = UIAPILayer(loop=RecordingLoop(), orchestrator=orch)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> None:
        async with app.run_test() as pilot:
            for ch in "/task ":
                await pilot.press(ch)
            await pilot.press("enter")
            for _ in range(10):
                await pilot.pause()

    asyncio.run(drive())
    assert orch.goals == []  # 空目标不启动任务


def test_task_command_busy_rejects_concurrent() -> None:
    """/task 运行期间再发消息提示等待（不并发放任务）。"""
    started = asyncio.Event()
    release = asyncio.Event()

    class _BlockingOrchestrator:
        """阻塞式编排器：started 后挂起，release 才收尾（忙态窗口确定）。"""

        async def astream(self, task_id: str, goal: str, **kwargs: object):
            started.set()
            await release.wait()
            yield LoopEvent("task_finished", {"outcomes": []})

    loop = RecordingLoop()
    api = UIAPILayer(loop=loop, orchestrator=_BlockingOrchestrator())
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> None:
        async with app.run_test() as pilot:
            for ch in "/task slow":
                await pilot.press(ch)
            await pilot.press("enter")
            for _ in range(50):
                await pilot.pause()
                if started.is_set():
                    break
            for ch in "hello":
                await pilot.press(ch)  # 任务运行中：提示等待，不进 loop
            await pilot.press("enter")
            for _ in range(10):
                await pilot.pause()
            assert loop.inputs == []  # 任务未收尾（仍忙）：消息未执行
            release.set()  # 放行收尾
            for _ in range(20):
                await pilot.pause()

    asyncio.run(drive())
    assert loop.inputs == []  # 忙时的 hello 未进普通对话


def test_task_subtask_collapsible_lifecycle() -> None:
    """子任务折叠块：标题随完成态落 ✓，展开区含验收/判定/结果节选。"""
    orch = _TaskOrchestrator(
        [
            ("task_started", {"task_id": "t1", "goal": "查答案"}),
            (
                "subtask_started",
                {"task_id": "t1", "subtask_id": "1", "goal": "查资料", "acceptance": "给出来源"},
            ),
            (
                "subtask_completed",
                {
                    "task_id": "t1",
                    "subtask_id": "1",
                    "ok": True,
                    "reason": "验收通过",
                    "reply": "答案 42",
                },
            ),
            ("task_finished", {"outcomes": []}),
        ]
    )
    api = UIAPILayer(loop=RecordingLoop(), orchestrator=orch)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> str:
        async with app.run_test() as pilot:
            from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
            from textual.widgets import Collapsible  # noqa: PLC0415 — 可选依赖懒 import

            for ch in "/task 查答案":
                await pilot.press(ch)
            await pilot.press("enter")
            for _ in range(50):  # 等 worker 跑完编排桩（事件即时产出）
                await pilot.pause()
                if orch.goals:
                    break
            for _ in range(5):
                await pilot.pause()
            box = app.query_one("#timeline", Vertical).query_one(Collapsible)
            contents = box.query_one(Collapsible.Contents)
            assert contents.display is False  # 验收/判定/结果藏折叠区（不直接显示）
            return _timeline_text(app)

    text = asyncio.run(drive())
    assert "▸ 子任务 1  ✓ 查资料" in text  # 完成后标题更新（单行提示）
    assert "验收：给出来源" in text  # 展开区：验收标准
    assert "判定：验收通过" in text  # 展开区：判定理由
    assert "答案 42" in text  # 展开区：结果节选


def test_tui_action_widget_lifecycle() -> None:
    """TUI 工具动作行：⏺ 折叠块标题随完成落 ✓+耗时，展开区含参数/输出。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())

    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    app = build_app(api)

    class _ActionLoop:
        """回放一轮工具动作事件 + 终态回复的 loop 替身。"""

        async def astream(self, user_input: str, *, session_id: str = ""):
            from core.loop import LoopEvent  # noqa: PLC0415 — 事件构造

            yield LoopEvent("loop_started", {"trace_id": "t1"})
            yield LoopEvent(
                "action_started",
                {"round": 0, "tool_id": "tools.code_run", "args": {"code": "print(1)"}},
            )
            yield LoopEvent(
                "action_completed",
                {
                    "round": 0,
                    "tool_id": "tools.code_run",
                    "ok": True,
                    "duration_ms": 1500,
                    "output": "1",
                },
            )
            yield LoopEvent("step_completed", {"round": 1, "failed": False})
            yield LoopEvent("loop_finished", {"reply": "done", "trace_id": "t1"})

    api._loop = _ActionLoop()  # noqa: SLF001 — 注入替身驱动事件面

    async def drive() -> str:
        async with app.run_test() as pilot:
            from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
            from textual.widgets import Collapsible, Input  # noqa: PLC0415 — 可选依赖懒 import

            inp = app.query_one("#input", Input)
            inp.focus()
            inp.value = "跑一下"
            await pilot.press("enter")
            for _ in range(30):
                await pilot.pause()
            box = app.query_one("#timeline", Vertical).query_one(Collapsible)
            contents = box.query_one(Collapsible.Contents)
            assert contents.display is False  # 输出藏折叠区（不直接显示）
            return _timeline_text(app)

    text = asyncio.run(drive())
    assert "⏺ Bash ✓ (1.5s)" in text  # 友好名 + 完成标题（tools.code_run → Bash）
    assert "参数" not in text  # 回显不含原始参数（args 不进用户可见层）
    assert "输出：1" in text  # 展开区：输出节选


# ---- TUI 思考回显（change 0145 / 账本 E60 呈现面）----


def test_tui_thinking_renders_in_single_collapsed_block() -> None:
    """TUI 思考回显：`loop.reasoning` 增量归并到**单个**缺省收起折叠块，主回复不受影响。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())

    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    app = build_app(api)

    class _ThinkingLoop:
        """回放思考增量、回复增量与终态的 loop 替身。"""

        async def astream(self, user_input: str, *, session_id: str = ""):
            from core.loop import LoopEvent  # noqa: PLC0415 — 事件构造

            yield LoopEvent("loop_started", {"trace_id": "t1"})
            yield LoopEvent("loop.reasoning", {"text": "先读文件"})
            yield LoopEvent("loop.reasoning", {"text": "，再改配置"})
            yield LoopEvent("reply_delta", {"text": "好了"})
            yield LoopEvent("loop_finished", {"reply": "好了", "trace_id": "t1"})

    api._loop = _ThinkingLoop()  # noqa: SLF001 — 注入替身驱动事件面

    async def drive() -> tuple[str, int, bool, str]:
        async with app.run_test() as pilot:
            from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
            from textual.widgets import Collapsible, Input  # noqa: PLC0415 — 可选依赖懒 import

            inp = app.query_one("#input", Input)
            inp.focus()
            inp.value = "怎么做"
            await pilot.press("enter")
            for _ in range(30):
                await pilot.pause()
            boxes = list(app.query_one("#timeline", Vertical).query(Collapsible))
            collapsed = [b.query_one(Collapsible.Contents).display is False for b in boxes]
            return _timeline_text(app), len(boxes), all(collapsed), str(app._last_reply)

    text, boxes, all_collapsed, reply = asyncio.run(drive())
    assert boxes == 1, "同轮思考增量归并到同一块（不逐段新建）"
    assert all_collapsed, "思考块缺省收起（标题可见、正文藏折叠区）"
    assert "思考" in text  # 折叠块标题
    assert "先读文件，再改配置" in text  # 增量按序拼接
    assert reply == "好了"  # 主回复呈现不受影响（终态收口原文）


# ---- TUI 流式结构化块整体解析（change 0146 / 账本 E88）----


def test_in_open_table_predicate() -> None:
    """`_in_open_table` 判据：当前块每行 ≥2 个 `|` ⇒ 未闭合表格；空行或块外内容即闭合。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())

    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    app = build_app(api)
    in_open_table = app._in_open_table  # noqa: SLF001 — 判据为应用内静态方法（同 _in_open_fence）

    assert in_open_table("| 水果 | 产地 |\n") is True  # 表头落定、分隔行未到 ⇒ 仍开
    assert in_open_table("| 水果 | 产地 |\n|---|---|\n| 苹果 | 烟台 |\n") is True
    assert in_open_table("| 水果 | 产地 |\n\n") is False  # 空行 ⇒ 表格块闭合
    assert in_open_table("| 水果 | 产地 |\n接下来是散文\n") is False  # 块外内容 ⇒ 闭合
    assert in_open_table("见 foo|bar\n") is False  # 单竖线散文 ⇒ 不误判
    assert in_open_table("```\n| 水果 | 产地 |\n") is False  # 围栏块（含 ``` 行）不判为表格


def test_streamed_table_renders_in_single_block() -> None:
    """流式 Markdown 表格按行到达 ⇒ 整体落入**单个** Markdown 块（不逐行拆成多块）。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())

    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    app = build_app(api)

    rows = ["| 水果 | 产地 |\n", "|---|---|\n", "| 苹果 | 烟台 |\n", "| 橙子 | 赣南 |\n"]

    class _TableLoop:
        """逐行回放表格分片的 loop 替身（行间让出控制权 ⇒ 尾块挂载与增量更新交错）。"""

        async def astream(self, user_input: str, *, session_id: str = ""):
            from core.loop import LoopEvent  # noqa: PLC0415 — 事件构造

            yield LoopEvent("loop_started", {"trace_id": "t1"})
            for row in rows:
                await asyncio.sleep(0.01)  # 真实流式分片节拍（挂载先于后续增量落定）
                yield LoopEvent("reply_delta", {"text": row})
            yield LoopEvent("loop_finished", {"reply": "<table>", "trace_id": "t1"})

    api._loop = _TableLoop()  # noqa: SLF001 — 注入替身驱动事件面

    async def drive() -> tuple[int, str, list[str]]:
        async with app.run_test() as pilot:
            from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
            from textual.widgets import Input, Markdown  # noqa: PLC0415 — 可选依赖懒 import

            inp = app.query_one("#input", Input)
            inp.focus()
            inp.value = "列个表"
            await pilot.press("enter")
            for _ in range(30):
                await pilot.pause()
            blocks = list(app.query_one("#timeline", Vertical).query(Markdown))
            kinds = [type(k).__name__ for b in blocks for k in b.query("*")]
            return len(blocks), "".join(str(b.source) for b in blocks), kinds

    count, source, kinds = asyncio.run(drive())
    assert count == 1, "表格整体落入单一 Markdown 块（不逐行固化拆块）"
    assert "MarkdownTable" in kinds, "整块被解析为表格（非逐行竖线段落）"
    assert "| 苹果 | 烟台 |" in source and "| 橙子 | 赣南 |" in source


# ---- TUI 流式回显合帧节流与表格延后渲染（change 0147 / 账本 E89）----


def test_show_delta_defers_until_flush() -> None:
    """合帧节流：delta 只入缓冲、不即时渲染；`_flush_tail` 把缓冲合并渲染一次。

    直接驱动 `_show_delta` / `_flush_tail`（不依赖 40ms 定时器真的触发 —— `pilot.pause()`
    实测是 ~0.02s 真实 sleep，与节拍同量级、会偶发触发，断言不得跨 `await`）。
    """
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())

    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    app = build_app(api)

    async def drive() -> tuple[bool, str, bool, int]:
        async with app.run_test() as pilot:
            from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
            from textual.widgets import Markdown  # noqa: PLC0415 — 可选依赖懒 import

            timeline = app.query_one("#timeline", Vertical)
            app._show_delta("你")  # noqa: SLF001 — 直接驱动流式入口（合帧前不渲染）
            app._show_delta("好")  # noqa: SLF001
            deferred = app._tail_widget is None  # 红态：旧实现逐 delta 立即建 widget
            buffered = "".join(app._tail_buf)
            app._flush_tail()  # noqa: SLF001 — 显式合帧（不依赖定时器）
            touched = app._tail_widget is not None
            await pilot.pause()
            return deferred, buffered, touched, len(timeline.query(Markdown))

    deferred, buffered, touched, rendered = asyncio.run(drive())
    assert deferred, "合帧前不渲染（不逐 delta 重绘）"
    assert buffered == "你好", "增量在缓冲里（不丢字）"
    assert touched, "合帧后尾块建立"
    assert rendered == 1, "合帧后渲染一次（增量合并为单块）"


def test_open_table_not_rendered_until_closed() -> None:
    """未闭合表格延后渲染：中间态不绘制；空行闭合后一次成型（恰一块、解析为表格）。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())

    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    app = build_app(api)

    async def drive() -> tuple[bool, bool, int, list[str]]:
        async with app.run_test() as pilot:
            from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
            from textual.widgets import Markdown  # noqa: PLC0415 — 可选依赖懒 import

            timeline = app.query_one("#timeline", Vertical)
            for row in ("| 水果 | 产地 |\n", "|---|---|\n", "| 苹果 | 烟台 |\n"):
                app._show_delta(row)  # noqa: SLF001
            app._flush_tail()  # noqa: SLF001 — 未闭合 ⇒ 延后（红态：旧实现已挂 Markdown）
            deferred = app._tail_widget is None
            buffered = bool(app._tail_buf)
            app._show_delta("\n")  # noqa: SLF001 — 空行 ⇒ 表格块闭合
            app._flush_tail()  # noqa: SLF001
            await pilot.pause()
            blocks = list(timeline.query(Markdown))
            kinds = [type(k).__name__ for b in blocks for k in b.query("*")]
            return deferred, buffered, len(blocks), kinds

    deferred, buffered, count, kinds = asyncio.run(drive())
    assert deferred, "未闭合表格不渲染中间态"
    assert buffered, "表格文本仍在缓冲（不丢字）"
    assert count == 1, "闭合后整块落入单一 Markdown 块"
    assert "MarkdownTable" in kinds, "闭合后解析为表格（非竖线原文）"


def test_open_fence_still_streams() -> None:
    """回归守卫：未闭合代码围栏**仍流式可见**（表格延后不得误伤围栏）。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())

    from core.ui.repl import build_app  # noqa: PLC0415 — 可选依赖懒 import

    app = build_app(api)

    async def drive() -> bool:
        async with app.run_test():
            app._show_delta("```python\n")  # noqa: SLF001
            app._show_delta("print(1)\n")  # noqa: SLF001
            app._flush_tail()  # noqa: SLF001
            return app._tail_widget is not None

    assert asyncio.run(drive()), "未闭合围栏合帧后仍渲染（流式可见）"


# ---- TUI 子任务运行态与里程碑详情（change 0124 / 账本 E52） ----


def _drive_task(app: object, goal: str, *, pauses: int = 60) -> str:
    """以 `/task <目标>` 驱动 headless app，返回时间线全量文本。"""

    async def drive() -> str:
        async with app.run_test() as pilot:  # type: ignore[attr-defined]
            for ch in f"/task {goal}":
                await pilot.press(ch)
            await pilot.press("enter")
            for _ in range(pauses):
                await pilot.pause()
            return _timeline_text(app)

    return asyncio.run(drive())


def test_subtask_milestones_render_in_collapsible_detail() -> None:
    """里程碑事件落子任务展开区：工具类复用动作行友好名（含耗时），轮次级落轮次与成败。"""
    orch = _TaskOrchestrator(
        [
            ("task_started", {"task_id": "t1", "goal": "查答案"}),
            (
                "subtask_started",
                {"task_id": "t1", "subtask_id": "1", "goal": "查资料", "acceptance": "给出来源"},
            ),
            (
                "subtask_progress",
                {
                    "task_id": "t1",
                    "subtask_id": "1",
                    "event": "action_started",
                    "data": {"round": 0, "tool_id": "tools.code_run", "args": {"code": "print(1)"}},
                    "ts": 1.0,
                },
            ),
            (
                "subtask_progress",
                {
                    "task_id": "t1",
                    "subtask_id": "1",
                    "event": "action_completed",
                    "data": {
                        "round": 0,
                        "tool_id": "tools.code_run",
                        "ok": True,
                        "duration_ms": 1500,
                        "output": "1",
                    },
                    "ts": 2.0,
                },
            ),
            (
                "subtask_progress",
                {
                    "task_id": "t1",
                    "subtask_id": "1",
                    "event": "step_completed",
                    "data": {"round": 1, "failed": False},
                    "ts": 3.0,
                },
            ),
            (
                "subtask_completed",
                {
                    "task_id": "t1",
                    "subtask_id": "1",
                    "ok": True,
                    "reason": "验收通过",
                    "reply": "答案 42",
                },
            ),
            ("task_finished", {"outcomes": []}),
        ]
    )
    api = UIAPILayer(loop=RecordingLoop(), orchestrator=orch)
    api.set_llm_config(_llm())

    text = _drive_task(build_app(api), "查答案")

    # 依序可见：验收 → 里程碑（开工/完成/轮次级）→ 判定 → 结果节选
    assert "验收：给出来源\n⏺ Bash\n⏺ Bash ✓ (1.5s)\n· 第 1 轮完成\n判定：验收通过\n答案 42" in text
    assert "tools.code_run" not in text  # 内部 tool_id 不进用户可见层
    assert "print(1)" not in text  # 原始参数不进用户可见层


def test_subtask_title_shows_running_mark_until_completion() -> None:
    """运行中徽标：开工后标题含运行中标记，收尾替换为 ✓（不并存）。"""
    started = asyncio.Event()
    release = asyncio.Event()

    class _BlockingOrchestrator:
        """阻塞式编排器：subtask_started 后挂起，release 才收尾（运行态窗口确定）。"""

        async def astream(self, task_id: str, goal: str, **kwargs: object):
            yield LoopEvent(
                "subtask_started",
                {"task_id": task_id, "subtask_id": "1", "goal": "查资料", "acceptance": ""},
            )
            started.set()
            await release.wait()
            yield LoopEvent(
                "subtask_completed",
                {"task_id": task_id, "subtask_id": "1", "ok": True, "reason": "ok"},
            )
            yield LoopEvent("task_finished", {"outcomes": []})

    api = UIAPILayer(loop=RecordingLoop(), orchestrator=_BlockingOrchestrator())
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> tuple[str, str]:
        from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
        from textual.widgets import Collapsible  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            for ch in "/task 查答案":
                await pilot.press(ch)
            await pilot.press("enter")
            for _ in range(50):
                await pilot.pause()
                if started.is_set():
                    break
            box = app.query_one("#timeline", Vertical).query_one(Collapsible)
            running = str(box.title)
            release.set()
            for _ in range(20):
                await pilot.pause()
            return running, str(box.title)

    running, done = asyncio.run(drive())
    assert "⟳" in running and "✓" not in running  # 运行中标记（尚未收尾）
    assert running.startswith("▸ 子任务 1")  # 主题（goal）与 sid 仍在
    assert done == "▸ 子任务 1  ✓ 查资料"  # 收尾替换为既有 ✓ 口径


def test_progress_for_unknown_subtask_is_ignored() -> None:
    """里程碑无对应折叠块（未知 id）⇒ 静默忽略：不新建块、不影响其它子任务详情。"""
    orch = _TaskOrchestrator(
        [
            (
                "subtask_started",
                {"task_id": "t", "subtask_id": "1", "goal": "查资料", "acceptance": "给出来源"},
            ),
            (
                "subtask_progress",
                {
                    "task_id": "t",
                    "subtask_id": "9",
                    "event": "action_started",
                    "data": {"round": 0, "tool_id": "tools.file_read", "args": {}},
                    "ts": 1.0,
                },
            ),
            (
                "subtask_progress",
                {
                    "task_id": "t",
                    "subtask_id": "1",
                    "event": "action_completed",
                    "data": {
                        "round": 0,
                        "tool_id": "tools.file_read",
                        "ok": True,
                        "duration_ms": 12,
                    },
                    "ts": 2.0,
                },
            ),
            ("task_finished", {"outcomes": []}),
        ]
    )
    api = UIAPILayer(loop=RecordingLoop(), orchestrator=orch)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> tuple[str, int]:
        from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
        from textual.widgets import Collapsible  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            for ch in "/task 查答案":
                await pilot.press(ch)
            await pilot.press("enter")
            for _ in range(60):
                await pilot.pause()
            boxes = len(app.query_one("#timeline", Vertical).query(Collapsible))
            return _timeline_text(app), boxes

    text, boxes = asyncio.run(drive())
    assert text.count("⏺ Read") == 1  # 未知 id（9）的里程碑被忽略；已知 id（1）的呈现一次
    assert "⏺ Read ✓ (12ms)" in text
    assert boxes == 1  # 未因里程碑新建折叠块


def test_non_action_progress_renders_no_line() -> None:
    """表外里程碑类型（非动作行、非轮次级）⇒ 不落任何行（不落空行与占位，不谎报）。"""
    orch = _TaskOrchestrator(
        [
            (
                "subtask_started",
                {"task_id": "t", "subtask_id": "1", "goal": "查资料", "acceptance": "给出来源"},
            ),
            (
                "subtask_progress",
                {
                    "task_id": "t",
                    "subtask_id": "1",
                    "event": "reason_started",
                    "data": {},
                    "ts": 1.0,
                },
            ),
            (
                "subtask_progress",
                {
                    "task_id": "t",
                    "subtask_id": "1",
                    "event": "action_completed",
                    "data": "非字典载荷",
                },
            ),
            (
                "subtask_progress",
                {
                    "task_id": "t",
                    "subtask_id": "1",
                    "event": "action_completed",
                    "data": {
                        "round": 0,
                        "tool_id": "tools.file_read",
                        "ok": True,
                        "duration_ms": 12,
                    },
                    "ts": 2.0,
                },
            ),
            ("task_finished", {"outcomes": []}),
        ]
    )
    api = UIAPILayer(loop=RecordingLoop(), orchestrator=orch)
    api.set_llm_config(_llm())

    text = _drive_task(build_app(api), "查答案")

    # 表外/异常载荷**不留痕**：验收后紧跟的正是合法里程碑（中间无空行与占位）
    assert "验收：给出来源\n⏺ Read ✓ (12ms)" in text
    assert "reason_started" not in text


# ---- TUI 子 Agent 焦点视图（change 0125 / 账本 E61） ----


def _panel_text(app: object) -> str:
    """焦点面板全量文本：标题（markup 口径）+ 正文（原始口径）渲染文本。"""
    from textual.widgets import Static  # noqa: PLC0415 — 可选依赖懒 import

    title = app.query_one("#panel-title", Static)  # type: ignore[attr-defined]
    body = app.query_one("#panel-body", Static)  # type: ignore[attr-defined]
    return f"{title.render()}{body.render()}"


class _GatedOrchestrator:
    """门控编排器：`subtask_started` 后挂起，按事件门放行里程碑与收尾（运行态窗口确定）。"""

    def __init__(self, *, milestone: asyncio.Event, done: asyncio.Event) -> None:
        self.started = asyncio.Event()
        self._milestone = milestone
        self._done = done

    async def astream(self, task_id: str, goal: str, **kwargs: object):
        yield LoopEvent("task_started", {"task_id": task_id, "goal": goal})
        yield LoopEvent(
            "subtask_started",
            {"task_id": task_id, "subtask_id": "1", "goal": "查资料", "acceptance": "给出来源"},
        )
        self.started.set()
        await self._milestone.wait()
        yield LoopEvent(
            "subtask_progress",
            {
                "task_id": task_id,
                "subtask_id": "1",
                "event": "action_completed",
                "data": {
                    "round": 0,
                    "tool_id": "tools.code_run",
                    "ok": True,
                    "duration_ms": 1500,
                    "output": "1",
                },
                "ts": 1.0,
            },
        )
        await self._done.wait()
        yield LoopEvent(
            "subtask_completed",
            {
                "task_id": task_id,
                "subtask_id": "1",
                "ok": True,
                "reason": "验收通过",
                "reply": "答案 42",
            },
        )
        yield LoopEvent("task_finished", {"outcomes": []})


async def _type_line(pilot: object, text: str) -> None:
    """逐字符输入并回车（headless 输入驱动，与既有 /task 用例同法）。"""
    for ch in text:
        await pilot.press(ch)  # type: ignore[attr-defined]
    await pilot.press("enter")  # type: ignore[attr-defined]


async def _wait_started(pilot: object, orch: _GatedOrchestrator) -> None:
    """等门控编排器的 `subtask_started` 事件到位（运行态窗口开启）。"""
    for _ in range(50):
        await pilot.pause()  # type: ignore[attr-defined]
        if orch.started.is_set():
            break


def test_focus_shows_subtask_panel_and_hides_timeline() -> None:
    """`/focus <sid>`：面板可见、主时间线不可见，且焦点命令**不进推理**。"""
    milestone, done = asyncio.Event(), asyncio.Event()
    orch = _GatedOrchestrator(milestone=milestone, done=done)
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop, orchestrator=orch)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> str:
        from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            await _type_line(pilot, "/task 查答案")
            await _wait_started(pilot, orch)
            await _type_line(pilot, "/focus 1")
            for _ in range(20):
                await pilot.pause()
            assert app.query_one("#panel", Vertical).display is True
            assert app.query_one("#timeline", Vertical).display is False
            focused = _panel_text(app)
            milestone.set()
            done.set()
            for _ in range(20):
                await pilot.pause()
            return focused

    focused = asyncio.run(drive())
    assert loop.inputs == []  # 焦点命令不进推理
    assert "▸ 子任务 1" in focused  # 主题（sid + goal）沿用折叠块口径
    assert "⟳" in focused  # 运行态徽标
    assert "验收：给出来源" in focused  # 详情：验收标准


def test_focus_panel_refreshes_on_milestone_and_completion() -> None:
    """聚焦期间**实时刷新**：里程碑补入正文，收尾后标题落 ✓ 且正文含判定。"""
    milestone, done = asyncio.Event(), asyncio.Event()
    orch = _GatedOrchestrator(milestone=milestone, done=done)
    api = UIAPILayer(loop=RecordingLoop(), orchestrator=orch)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> tuple[str, str]:
        async with app.run_test() as pilot:  # type: ignore[attr-defined]
            await _type_line(pilot, "/task 查答案")
            await _wait_started(pilot, orch)
            await _type_line(pilot, "/focus 1")
            for _ in range(10):
                await pilot.pause()
            milestone.set()
            for _ in range(30):
                await pilot.pause()
            mid = _panel_text(app)
            done.set()
            for _ in range(30):
                await pilot.pause()
            return mid, _panel_text(app)

    mid, after = asyncio.run(drive())
    assert "⏺ Bash ✓ (1.5s)" in mid  # 里程碑：友好名 + 耗时（复用动作行口径）
    assert "✓" in after and "⟳" not in after  # 收尾替换运行态徽标
    assert "判定：验收通过" in after
    assert "答案 42" in after  # 结果节选


def test_returning_to_main_view_leaves_timeline_unchanged() -> None:
    """`/main` 回主视图：时间线重新可见且文本与聚焦前**逐字一致**（呈现层切换不改内容）。"""
    milestone, done = asyncio.Event(), asyncio.Event()
    orch = _GatedOrchestrator(milestone=milestone, done=done)
    api = UIAPILayer(loop=RecordingLoop(), orchestrator=orch)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> tuple[str, str, bool]:
        from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            await _type_line(pilot, "/task 查答案")
            await _wait_started(pilot, orch)
            before = _timeline_text(app)
            await _type_line(pilot, "/focus 1")
            for _ in range(10):
                await pilot.pause()
            assert app.query_one("#timeline", Vertical).display is False
            await _type_line(pilot, "/main")
            for _ in range(10):
                await pilot.pause()
            visible = app.query_one("#timeline", Vertical).display is True
            after = _timeline_text(app)
            milestone.set()
            done.set()
            for _ in range(20):
                await pilot.pause()
            return before, after, visible

    before, after, visible = asyncio.run(drive())
    assert visible
    assert after == before  # 聚焦/返回**零时间线写入**


def test_focus_command_bypasses_busy_rejection() -> None:
    """任务运行中（忙态）：`F2` 仍生效（焦点命令先于忙态拒绝被处理），忙态不复位。"""
    milestone, done = asyncio.Event(), asyncio.Event()
    orch = _GatedOrchestrator(milestone=milestone, done=done)
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop, orchestrator=orch)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> bool:
        from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            await _type_line(pilot, "/task 查答案")
            await _wait_started(pilot, orch)
            await _type_line(pilot, "/focus 1")
            for _ in range(10):
                await pilot.pause()
            assert app.query_one("#panel", Vertical).display is True
            await pilot.press("f2")  # 忙态中直接按键（不回车）
            for _ in range(10):
                await pilot.pause()
            back = app.query_one("#timeline", Vertical).display is True
            busy = app._turn_busy  # noqa: SLF001 — 断言忙态未被焦点命令复位
            milestone.set()
            done.set()
            for _ in range(20):
                await pilot.pause()
            return back and busy

    assert asyncio.run(drive())
    assert loop.inputs == []  # 焦点命令与 F2 均不进推理


def test_focus_unknown_subtask_keeps_main_view() -> None:
    """未开工即聚焦 / 未知标识：均**不切换**视图（主时间线仍在），并给未找到提示。"""
    orch = _TaskOrchestrator(
        [
            (
                "subtask_started",
                {"task_id": "t", "subtask_id": "1", "goal": "查资料", "acceptance": "给出来源"},
            ),
            ("task_finished", {"outcomes": []}),
        ]
    )
    api = UIAPILayer(loop=RecordingLoop(), orchestrator=orch)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> tuple[bool, bool, str]:
        from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            await _type_line(pilot, "/focus 1")  # 未开工即聚焦（尚无对应折叠块）
            for _ in range(10):
                await pilot.pause()
            early = app.query_one("#panel", Vertical).display
            await _type_line(pilot, "/task 查答案")
            for _ in range(60):
                await pilot.pause()
            await _type_line(pilot, "/focus 99")  # 未知标识
            for _ in range(10):
                await pilot.pause()
            return early, app.query_one("#panel", Vertical).display, _timeline_text(app)

    early, panel, text = asyncio.run(drive())
    assert early is False  # 未开工即聚焦：不进入焦点视图（无「延迟聚焦」半开态）
    assert panel is False  # 未知标识：仍为主视图
    assert "未找到子任务 99" in text


def test_focus_panel_does_not_leak_tool_id_or_args() -> None:
    """焦点面板沿用友好名口径：不含内部 `tool_id` 与工具原始参数。"""
    milestone, done = asyncio.Event(), asyncio.Event()
    orch = _GatedOrchestrator(milestone=milestone, done=done)
    api = UIAPILayer(loop=RecordingLoop(), orchestrator=orch)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> str:
        async with app.run_test() as pilot:  # type: ignore[attr-defined]
            await _type_line(pilot, "/task 查答案")
            await _wait_started(pilot, orch)
            milestone.set()
            for _ in range(30):
                await pilot.pause()
            await _type_line(pilot, "/focus 1")
            for _ in range(10):
                await pilot.pause()
            panel = _panel_text(app)
            done.set()
            for _ in range(20):
                await pilot.pause()
            return panel

    panel = asyncio.run(drive())
    assert "Bash" in panel  # 友好名
    assert "tools.code_run" not in panel  # 内部 tool_id 不进用户可见层
    assert "print(1)" not in panel  # 原始参数不进用户可见层


# ---- 会话续聊（`--session <id>`，change 0116） ----


def _api_with_history(turns: list[tuple[str, str]]) -> tuple[UIAPILayer, str]:
    """真 `TranscriptStore` + 已发生若干轮的会话（返回 api 与 session_id）。"""
    transcript = TranscriptStore()
    api = UIAPILayer(loop=RecordingLoop(), transcript=transcript)
    api.set_llm_config(_llm())
    session_id = api.create_session("cli")
    for user, reply in turns:
        transcript.append(session_id, "user", user)
        transcript.append(session_id, "assistant", reply)
    return api, session_id


def _timeline_texts(app: object) -> list[str]:
    """时间线内全部可见文本：`Static` 取 `render()`，`Markdown`（agent 回复）取源文本。"""

    async def drive() -> list[str]:
        async with app.run_test() as pilot:  # type: ignore[attr-defined]
            for _ in range(5):
                await pilot.pause()
            static = [str(w.render()) for w in app.query("#timeline Static")]  # type: ignore[attr-defined]
            markdown = [str(w.source) for w in app.query("#timeline Markdown")]  # type: ignore[attr-defined]
            return static + markdown

    return asyncio.run(drive())


def _timeline_markdown(app: object) -> tuple[int, list[str]]:
    """时间线内（`MarkdownFence` 数，各 `Markdown` 块源文本）——续聊回放的格式面。"""

    async def drive() -> tuple[int, list[str]]:
        async with app.run_test() as pilot:  # type: ignore[attr-defined]
            from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
            from textual.widgets import Markdown  # noqa: PLC0415 — 可选依赖懒 import

            for _ in range(5):
                await pilot.pause()
            blocks = list(app.query_one("#timeline", Vertical).query(Markdown))  # type: ignore[attr-defined]
            kinds = [type(k).__name__ for b in blocks for k in b.query("*")]
            return kinds.count("MarkdownFence"), [str(b.source) for b in blocks]

    return asyncio.run(drive())


def test_build_app_resumes_existing_session(monkeypatch) -> None:
    """`--session <id>` 续聊：复用既有会话（不新建），既有转录渲染进时间线。"""
    api, session_id = _api_with_history([("早前的问题", "早前的回答")])
    monkeypatch.setattr(api, "create_session", lambda *a, **kw: pytest.fail("不应新建会话"))

    texts = _timeline_texts(build_app(api, session_id))

    assert any("早前的问题" in text for text in texts)
    assert any("早前的回答" in text for text in texts)


def test_resumed_agent_reply_renders_as_markdown() -> None:
    """续聊铺入既有转录：**agent 回复**按 Markdown 渲染（围栏成代码块），与实时路径同格式；
    用户回显仍为 `❯` 行。（change 0157 / ADR-0149 —— 修复前该回复落 `Static` 明文。）"""
    reply = "示例：\n\n```python\nprint('hi')\n```\n"
    api, session_id = _api_with_history([("给我个 demo", reply)])

    fences, sources = _timeline_markdown(build_app(api, session_id))

    assert fences >= 1, "续聊转录里的代码围栏应渲染为代码块（非明文逐行）"
    assert any("```python" in src for src in sources)


_SRGB_LINEAR_CUTOFF = 0.03928  # WCAG sRGB → 线性 的分段阈值
_OPAQUE_ALPHA = 1.0  # 代码块背景 SHALL 完全不透明（change 0158）
_MIN_CODE_BLOCK_CONTRAST = 2.0  # 代码块背景与主背景的最低可辨对比度（change 0158）


def _luminance(rgb: tuple[float, float, float]) -> float:
    """WCAG 相对亮度（sRGB → 线性）。"""

    def channel(value: float) -> float:
        value /= 255.0
        return value / 12.92 if value <= _SRGB_LINEAR_CUTOFF else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (channel(v) for v in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """WCAG 对比度（1.0 = 同色不可辨，21.0 = 黑白极值）。"""
    la, lb = _luminance(a), _luminance(b)
    high, low = max(la, lb), min(la, lb)
    return (high + 0.05) / (low + 0.05)


def _code_block_background(app: object) -> tuple[float, float]:
    """时间线内首个 `MarkdownFence` 的解析后背景 —— 返回 `(不透明度, 与主背景的 WCAG 对比度)`。

    背景色（含 CSS 变量）在**运行时**解析；半透明前景先**叠加**到 TUI 主背景再算对比度
    （用户看到的是叠加后的实际色，不是色值本身）。"""

    async def drive() -> tuple[float, float]:
        from textual.color import Color  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:  # type: ignore[attr-defined]
            for _ in range(5):
                await pilot.pause()
            fence = next(iter(app.query("MarkdownFence")))  # type: ignore[attr-defined]
            color = fence.styles.background
            assert isinstance(color, Color), f"代码块背景应解析为具体色值，实得 {color!r}"
            alpha = color.a if color.a is not None else 1.0
            base = Color.parse(app.get_css_variables()["background"])  # type: ignore[attr-defined]
            shown = (
                alpha * color.r + (1 - alpha) * base.r,
                alpha * color.g + (1 - alpha) * base.g,
                alpha * color.b + (1 - alpha) * base.b,
            )
            return alpha, _contrast_ratio(shown, (base.r, base.g, base.b))

    return asyncio.run(drive())


def test_code_block_background_is_distinguishable() -> None:
    """代码块背景 SHALL **不透明**、且与主背景的 WCAG 对比度 SHALL **≥ 2.0** ⇒ 一眼可辨。
    修复前 Textual 默认 `background: black 10%` 在 `#121212` 上合成为 `#101010`（对比度 ≈ 1.02），
    等同没渲染。（change 0158 / ADR-0150 —— 用户实测「和主框颜色没差异，无法识别」。）"""
    reply = "示例：\n\n```python\nprint('hi')\n```\n"
    api, session_id = _api_with_history([("给我个 demo", reply)])

    alpha, ratio = _code_block_background(build_app(api, session_id))

    assert alpha == _OPAQUE_ALPHA, f"代码块背景应不透明（实得 alpha={alpha}）"
    assert ratio >= _MIN_CODE_BLOCK_CONTRAST, f"代码块背景对比度应 ≥ 2.0（实得 {ratio:.2f}）"


def test_build_app_rejects_unknown_session() -> None:
    """续接未登记会话：fail-closed 抛 `UiError`，且不静默新建会话顶替。"""
    api = UIAPILayer(loop=RecordingLoop())
    api.set_llm_config(_llm())

    with pytest.raises(UiError):
        build_app(api, "nope")

    assert api.list_sessions() == []


def test_build_app_default_creates_session() -> None:
    """缺省不传 `session_id`：新建会话（既有行为不变）。"""
    api = UIAPILayer(loop=RecordingLoop())
    api.set_llm_config(_llm())

    build_app(api)

    assert len(api.list_sessions()) == 1


# ---- 神兽斜杠命令解析（change 0137 / 账本 E74） ----


def test_parse_beast_command_forms() -> None:
    """`/summon <神兽> [任务]` · `/recall <神兽>` 形态解析（非法形态返回 None）。"""
    assert _parse_beast_command("/summon qinglong 架构设计") == ("summon", "qinglong", "架构设计")
    assert _parse_beast_command("/summon qinglong") == ("summon", "qinglong", "")
    assert _parse_beast_command("/recall 青龙") == ("recall", "青龙", "")
    assert _parse_beast_command("/summon") is None  # 无目标
    assert _parse_beast_command("/summon   ") is None
    assert _parse_beast_command("/recall") is None
    assert _parse_beast_command("你好") is None
    assert _parse_beast_command("/focus s1") is None


# ---- 斜杠命令浮层与补全（change 0159 / ADR-0151） ----


def test_palette_options_lists_all_commands_on_slash() -> None:
    """输入 `/` ⇒ 列出单一真源内的全部命令（顺序即真源顺序）。"""
    assert [c.fill for c in _palette_options("/")] == [
        "/task",
        "/focus",
        "/main",
        "/summon",
        "/recall",
    ]


def test_palette_options_filters_by_command_prefix() -> None:
    """候选按前缀收窄（只认命令名前缀）。"""
    assert [c.fill for c in _palette_options("/ta")] == ["/task"]
    assert [c.fill for c in _palette_options("/re")] == ["/recall"]


def test_palette_options_closed_for_unknown_or_plain_input() -> None:
    """未知前缀 / 普通消息 / 空输入 / 带参命令已进参数位 ⇒ 均不呈现。"""
    assert _palette_options("/zzz") == []
    assert _palette_options("hi") == []
    assert _palette_options("") == []
    assert _palette_options("/task ") == []  # 参数不可枚举 ⇒ 无二级


def test_palette_options_second_level_lists_and_narrows_subtasks() -> None:
    """二级候选取既有子任务标识，并同样按前缀收窄。"""
    assert [c.fill for c in _palette_options("/focus ", subtask_ids=["1", "2"])] == [
        "/focus 1",
        "/focus 2",
    ]
    assert [c.fill for c in _palette_options("/focus 2", subtask_ids=["1", "2"])] == ["/focus 2"]


def test_palette_options_closed_when_arg_has_space() -> None:
    """参数位内出现空格（自由文本参数）⇒ 不呈现（不与普通对话抢键）。"""
    assert _palette_options("/focus 1 x", subtask_ids=["1"]) == []
    assert _palette_options("/summon qinglong 架构设计") == []


def test_palette_options_no_second_level_for_non_enum_arg() -> None:
    """参数**不可枚举**的命令（`/summon` `/task`）不进二级。"""
    assert _palette_options("/summon qinglong") == []
    assert _palette_options("/task build") == []


def test_palette_options_arg_next_marks_commands_taking_arg() -> None:
    """带参数命令采纳后补出参数位（`arg_next`），无参命令不补。"""
    by_fill = {c.fill: c for c in _palette_options("/")}
    assert by_fill["/task"].arg_next is True
    assert by_fill["/focus"].arg_next is True
    assert by_fill["/main"].arg_next is False


def _palette_api(*, orchestrator: object | None = None) -> tuple[UIAPILayer, RecordingLoop]:
    """浮层用例的 api：真 `RecordingLoop` + 可选编排器桩（LLM 已配置）。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop, orchestrator=orchestrator)
    api.set_llm_config(_llm())
    return api, loop


def _palette_display(app: object) -> bool:
    """浮层是否可见（`display` 翻转即开合）。"""
    from textual.widgets import OptionList  # noqa: PLC0415 — 可选依赖懒 import

    return bool(app.query_one("#palette", OptionList).display)  # type: ignore[attr-defined]


def _palette_option_ids(app: object) -> list[str | None]:
    """浮层当前候选的 id 列表（`cmd:<名>` / `arg:<标识>`）。"""
    from textual.widgets import OptionList  # noqa: PLC0415 — 可选依赖懒 import

    opts = app.query_one("#palette", OptionList).options  # type: ignore[attr-defined]
    return [o.id for o in opts]


def test_palette_opens_on_slash_and_lists_registered_commands() -> None:
    """输入 `/` ⇒ 浮层可见并列出单一真源内的既有 5 命令（`/resume` 属 0160，此处不登记）。"""
    api, _ = _palette_api()
    app = build_app(api)

    async def drive() -> list[str | None]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            app.query_one("#input", Input).focus()
            await pilot.press("/")
            await pilot.pause()
            assert _palette_display(app) is True
            return _palette_option_ids(app)

    assert asyncio.run(drive()) == [
        "cmd:/task",
        "cmd:/focus",
        "cmd:/main",
        "cmd:/summon",
        "cmd:/recall",
    ]


def test_palette_closes_when_input_cleared() -> None:
    """清空输入 ⇒ 浮层收起。"""
    api, _ = _palette_api()
    app = build_app(api)

    async def drive() -> tuple[bool, bool]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            app.query_one("#input", Input).focus()
            await pilot.press("/")
            await pilot.pause()
            opened = _palette_display(app)
            await pilot.press("backspace")
            await pilot.pause()
            return opened, _palette_display(app)

    assert asyncio.run(drive()) == (True, False)


def test_palette_arrows_move_highlight_keeping_focus_in_input() -> None:
    """`↑`/`↓` 移动高亮，**焦点仍留在输入框**（浮层不可聚焦）。"""
    api, _ = _palette_api()
    app = build_app(api)

    async def drive() -> tuple[object, object, object]:
        from textual.widgets import Input, OptionList  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            app.query_one("#input", Input).focus()
            await pilot.press("/")
            await pilot.pause()
            palette = app.query_one("#palette", OptionList)
            palette.highlighted = None  # 起点复位（避免依赖初始高亮策略）
            await pilot.press("down")
            await pilot.pause()
            first = palette.highlighted
            await pilot.press("down")
            await pilot.pause()
            return first, palette.highlighted, getattr(app.focused, "id", None)

    first, second, focused = asyncio.run(drive())
    assert first == 0
    assert isinstance(second, int) and second != first
    assert focused == "input"


def test_palette_tab_accepts_highlighted_command_without_submitting() -> None:
    """`Tab` 采纳高亮项：补出参数位、**不提交**，且不把焦点带走（App 默认 Tab 焦点后移被扣下）。"""
    api, loop = _palette_api()
    app = build_app(api)

    async def drive() -> tuple[str, object]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            app.query_one("#input", Input).focus()
            for ch in "/fo":
                await pilot.press(ch)
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            return app.query_one("#input", Input).value, getattr(app.focused, "id", None)

    value, focused = asyncio.run(drive())
    assert value == "/focus "  # 采纳：命令 + 参数位（不提交）
    assert focused == "input"
    assert loop.inputs == []


def test_palette_enter_completes_prefix_without_submitting() -> None:
    """浮层打开且输入为高亮项**前缀**时，`Enter` 只补全、不提交（避免与 `Submitted` 双执行）。"""
    api, loop = _palette_api()
    app = build_app(api)

    async def drive() -> str:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            app.query_one("#input", Input).focus()
            for ch in "/ta":
                await pilot.press(ch)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            return app.query_one("#input", Input).value

    assert asyncio.run(drive()) == "/task "
    assert loop.inputs == []


def test_palette_escape_closes_without_touching_input() -> None:
    """`Esc` 收起浮层，输入框文本不变。"""
    api, _ = _palette_api()
    app = build_app(api)

    async def drive() -> tuple[str, bool]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            app.query_one("#input", Input).focus()
            await pilot.press("/")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            return app.query_one("#input", Input).value, _palette_display(app)

    assert asyncio.run(drive()) == ("/", False)


def test_palette_does_not_hijack_unknown_slash_input() -> None:
    """**零回归**：未知前缀（`/zzz`）浮层不呈现，`Enter` 走既有路径（进普通对话）。"""
    api, loop = _palette_api()
    app = build_app(api)

    async def drive() -> bool:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            app.query_one("#input", Input).focus()
            for ch in "/zzz":
                await pilot.press(ch)
            await pilot.pause()
            assert _palette_display(app) is False
            await pilot.press("enter")
            for _ in range(10):
                await pilot.pause()
            return _palette_display(app)

    closed = asyncio.run(drive())
    assert closed is False
    assert loop.inputs == ["/zzz"]  # 未知前缀仍是普通消息（分发命运不变）


def test_palette_absent_keeps_arrows_and_escape_inert() -> None:
    """浮层未呈现时 `↑`/`↓`/`Esc` **零影响**（`Input` 本就不绑定这三键）。"""
    api, _ = _palette_api()
    app = build_app(api)

    async def drive() -> tuple[str, object]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            app.query_one("#input", Input).focus()
            await pilot.press("h", "i")
            await pilot.pause()
            await pilot.press("up", "down", "escape")
            await pilot.pause()
            return app.query_one("#input", Input).value, getattr(app.focused, "id", None)

    value, focused = asyncio.run(drive())
    assert value == "hi"
    assert focused == "input"


def test_palette_suppressed_while_approval_pending() -> None:
    """**审批挂起**期间不呈现浮层（y/n 决断输入不被遮蔽或改写）。"""
    api, _ = _palette_api()
    app = build_app(api)

    async def drive() -> tuple[bool, str]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            app._approval_future = asyncio.get_running_loop().create_future()  # noqa: SLF001
            inp.value = "/"
            await pilot.pause()
            shown = _palette_display(app)
            app._approval_future = None  # noqa: SLF001
            return shown, inp.value

    shown, value = asyncio.run(drive())
    assert shown is False
    assert value == "/"  # 输入未被魔改


def test_palette_second_level_lists_live_subtask_ids() -> None:
    """二级候选取自**既有**在途子任务面（`self._open` 的键），零新增数据源。"""
    milestone, done = asyncio.Event(), asyncio.Event()
    orch = _GatedOrchestrator(milestone=milestone, done=done)
    api, _ = _palette_api(orchestrator=orch)
    app = build_app(api)

    async def drive() -> list[str | None]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            await _type_line(pilot, "/task 查答案")
            await _wait_started(pilot, orch)
            inp.value = "/focus "  # 命令 + 空格 ⇒ 进二级
            await pilot.pause()
            ids = _palette_option_ids(app)
            milestone.set()
            done.set()
            for _ in range(20):
                await pilot.pause()
            return ids

    assert asyncio.run(drive()) == ["arg:1"]


def test_palette_second_level_fill_targets_subtask() -> None:
    """二级采纳后写入 `/focus <标识>`（可直接回车执行既有焦点命令）。"""
    milestone, done = asyncio.Event(), asyncio.Event()
    orch = _GatedOrchestrator(milestone=milestone, done=done)
    api, _ = _palette_api(orchestrator=orch)
    app = build_app(api)

    async def drive() -> str:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            await _type_line(pilot, "/task 查答案")
            await _wait_started(pilot, orch)
            inp.value = "/focus "
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            value = inp.value
            milestone.set()
            done.set()
            for _ in range(20):
                await pilot.pause()
            return value

    assert asyncio.run(drive()) == "/focus 1"


def test_ghost_completion_shows_and_accepts_remainder() -> None:
    """内联幽灵补全：命令名前缀 ⇒ 补出剩余字符，`→` 采纳（与浮层候选同源）。"""
    api, _ = _palette_api()
    app = build_app(api)

    async def drive() -> tuple[str | None, str]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            for ch in "/re":
                await pilot.press(ch)
            await pilot.pause()
            suggestion = inp._suggestion  # noqa: SLF001 — 断言补全建议（原生私有属性）
            await pilot.press("right")
            await pilot.pause()
            return suggestion, inp.value

    suggestion, value = asyncio.run(drive())
    assert suggestion == "/recall"
    assert value == "/recall"


def test_registry_commands_are_all_dispatchable() -> None:
    """**单一真源的可执行守护**：真源内每条命令都被分发链**消费**（不落普通对话）。

    任一条只登记、未接线（如尚未进表的 `/resume`），本用例即红。
    """
    orch = _TaskOrchestrator([("task_finished", {"outcomes": []})])
    api, loop = _palette_api(orchestrator=orch)
    app = build_app(api)

    async def drive() -> None:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            for line in ("/task 目标", "/focus 1", "/main", "/summon qinglong", "/recall qinglong"):
                inp.value = line
                await pilot.press("enter")
                for _ in range(30):
                    await pilot.pause()

    asyncio.run(drive())
    assert loop.inputs == []  # 全部被分发链消费（无一落进普通对话）
