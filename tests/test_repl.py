"""repl 单元测试（对齐契约红线：多轮上下文 / 空输入/EOF 退出 / barge-in 打断 / 错误降级）。"""

from __future__ import annotations

import asyncio

from core.configuration.models import LLMConfig
from core.loop import LoopEvent, LoopResult
from core.ui import Event, UIAPILayer, UiErrorCode
from core.ui.repl import _format_event, barge_in_event, build_app, format_task_event, repl_loop


class RecordingLoop:
    """记录每次输入并回显的 loop 替身（区分多轮）。"""

    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def astream(self, user_input: str):
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
    assert _format_event(Event("loop.result", {"text": "你好"})) == "你好"
    assert _format_event(Event("loop.result", {"reply": "echo:hi"})) == "echo:hi"
    assert _format_event(Event("loop.result", LoopResult(reply="hi", trace_id="t"))) is None
    assert _format_event(Event("loop.error", {"reason": "LOOP_LIMIT_EXCEEDED"})) == (
        "[loop.error] LOOP_LIMIT_EXCEEDED"
    )
    assert _format_event(Event("error", {"code": "X", "message": "m"})) == "[X] m"


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
            for ch in "/task 查答案":
                await pilot.press(ch)
            await pilot.press("enter")
            for _ in range(50):  # 等 worker 跑完编排桩（事件即时产出）
                await pilot.pause()
                if orch.goals:
                    break
            for _ in range(5):
                await pilot.pause()
            return _timeline_text(app)

    text = asyncio.run(drive())
    assert "▸ 子任务 1  ✓ 查资料" in text  # 完成后标题更新（单行提示）
    assert "验收：给出来源" in text  # 展开区：验收标准
    assert "判定：验收通过" in text  # 展开区：判定理由
    assert "答案 42" in text  # 展开区：结果节选
