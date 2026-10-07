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
    async def drive() -> list[str]:
        async with app.run_test() as pilot:  # type: ignore[attr-defined]
            await pilot.pause()
            return [str(w.render()) for w in app.query("#timeline Static")]  # type: ignore[attr-defined]

    return asyncio.run(drive())


def test_build_app_resumes_existing_session(monkeypatch) -> None:
    """`--session <id>` 续聊：复用既有会话（不新建），既有转录渲染进时间线。"""
    api, session_id = _api_with_history([("早前的问题", "早前的回答")])
    monkeypatch.setattr(api, "create_session", lambda *a, **kw: pytest.fail("不应新建会话"))

    texts = _timeline_texts(build_app(api, session_id))

    assert any("早前的问题" in text for text in texts)
    assert any("早前的回答" in text for text in texts)


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
