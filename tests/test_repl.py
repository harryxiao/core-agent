"""repl 单元测试（对齐契约红线：多轮上下文 / 空输入/EOF 退出 / barge-in 打断 / 错误降级）。"""

from __future__ import annotations

import asyncio

import pytest

from core.configuration.models import LLMConfig
from core.loop import LoopEvent, LoopResult
from core.memory import TranscriptStore
from core.ui import Event, UIAPILayer, UiError, UiErrorCode
from core.ui.repl import _format_event, barge_in_event, build_app, format_task_event, repl_loop


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
