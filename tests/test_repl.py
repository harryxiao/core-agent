"""repl 单元测试（对齐契约红线：多轮上下文 / 空输入/EOF 退出 / barge-in 打断 / 错误降级）。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from core.configuration import ConfigManager
from core.configuration.models import LLMConfig
from core.diagnostics import Deps
from core.loop import LoopEvent, LoopResult
from core.memory import ChainNode, TranscriptStore
from core.ui import Event, UIAPILayer, UiError, UiErrorCode
from core.ui.repl import (
    _COMMANDS,
    _MAX_TARGET_CHARS,
    _TAB_MAX_CHARS,
    _action_title,
    _event_delta,
    _format_event,
    _palette_options,
    _parse_beast_command,
    _tool_target,
    barge_in_event,
    build_app,
    format_task_event,
    repl_loop,
)


class RecordingLoop:
    """记录每次输入并回显的 loop 替身（区分多轮）。"""

    def __init__(self) -> None:
        self.inputs: list[str] = []
        self.sessions: list[str] = []  # 每轮收到的会话标识（会话切换的断言面）

    async def astream(self, user_input: str, *, session_id: str = ""):
        self.inputs.append(user_input)
        self.sessions.append(session_id)
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


def test_format_event_renders_compaction_progress() -> None:
    """压实进度事件渲染为单行提示（change 0256）。"""
    assert _format_event(Event("loop.compacting", {"round": 1})) == "上下文压缩中…"
    assert (
        _format_event(
            Event("loop.compacted", {"round": 1, "elapsed_ms": 38153.2, "timeout": False})
        )
        == "上下文已压缩（38153ms）"
    )
    assert (
        _format_event(
            Event("loop.compacted", {"round": 1, "elapsed_ms": 120000.0, "timeout": True})
        )
        == "上下文已压缩（120000ms）（超时放行）"
    )


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
    assert format_task_event("plan_ready", {"subtasks": [{"id": "1"}], "waves": [["1"]]}) == (
        "Planner(1 subtasks)"
    )
    assert format_task_event(
        "plan_ready", {"goal": "复合目标", "subtasks": [{"id": "1"}], "waves": [["1"]]}
    ) == ("Planner(复合目标)")
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
    assert "子任务 1  ✓ 查资料" in text  # 完成后标题更新（无 ▸；ui-scheme）
    assert "▸" not in text
    assert "验收：给出来源" in text  # 展开区：验收标准
    assert "判定：验收通过" in text  # 展开区：判定理由
    assert "答案 42" in text  # 展开区：结果节选


def test_tui_action_widget_lifecycle() -> None:
    """TUI 工具动作：`Shell(...)` 标题随完成落耗时；**缺省收起**；展开后可见输出。"""
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
                {"round": 0, "tool_id": "tools.code_run", "args": {"script": "print(1)"}},
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
            from textual.widgets import Collapsible, Input  # noqa: PLC0415 — 可选依赖懒 import

            inp = app.query_one("#input", Input)
            inp.focus()
            inp.value = "跑一下"
            await pilot.press("enter")
            for _ in range(30):
                await pilot.pause()
            box = _blocks(app)[0]
            contents = box.query_one(Collapsible.Contents)
            assert box.collapsed is True
            assert contents.display is False  # 缺省**收起**
            assert await pilot.click(box.query_one("CollapsibleTitle"))
            await pilot.pause()
            return _timeline_text(app)

    text = asyncio.run(drive())
    assert "Shell(print(1)) · 1.5s" in text
    assert "⏺" not in text
    assert "'script'" not in text
    assert "1" in text  # 展开后可见输出


# ---- TUI 步骤块（ui-scheme / 0233：缺省收起；展开即全文）----

_LONG_LINES = 20
_LONG_OUTPUT = "\n".join(f"第 {i} 行" for i in range(1, _LONG_LINES + 1))


def _step_app(output: str, *, script: str = "print(1)") -> object:
    """构造 app 并注入「一轮工具动作 + 给定输出」的 loop 替身（步骤块用例复用）。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())
    app = build_app(api)

    class _StepLoop:
        async def astream(self, user_input: str, *, session_id: str = ""):
            from core.loop import LoopEvent  # noqa: PLC0415 — 事件构造

            yield LoopEvent("loop_started", {"trace_id": "t1"})
            yield LoopEvent(
                "action_started",
                {"round": 0, "tool_id": "tools.code_run", "args": {"script": script}},
            )
            yield LoopEvent(
                "action_completed",
                {
                    "round": 0,
                    "tool_id": "tools.code_run",
                    "ok": True,
                    "duration_ms": 12,
                    "output": output,
                },
            )
            yield LoopEvent("loop_finished", {"reply": "done", "trace_id": "t1"})

    api._loop = _StepLoop()  # noqa: SLF001 — 注入替身驱动事件面
    return app


async def _step_submit(pilot: object) -> None:
    """提交一句话并等事件流落定（步骤块已建）。"""
    from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

    inp = pilot.app.query_one("#input", Input)
    inp.focus()
    inp.value = "跑一下"
    await pilot.press("enter")
    for _ in range(30):
        await pilot.pause()


def _blocks(app: object) -> list[object]:
    """时间线上的步骤块（Thinking / Read / Bash…）。"""
    from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
    from textual.widgets import Collapsible  # noqa: PLC0415 — 可选依赖懒 import

    return list(app.query_one("#timeline", Vertical).query(Collapsible))


def _inner(block: object, selector: str) -> object:
    from textual.widgets import Static  # noqa: PLC0415 — 可选依赖懒 import

    return block.query_one(selector, Static)


def test_tool_target_whitelist() -> None:
    """目标摘要**只取白名单结构性字段**（单行 + 有界）；未知工具 / 缺字段 / 非映射 ⇒ ""。"""
    cases: list[tuple[object, object, str]] = [
        ("tools.file_read", {"path": "src/a.py"}, "src/a.py"),
        ("tools.file_write", {"path": "x.py", "content": "整篇正文"}, "x.py"),
        ("tools.file_patch", {"path": "y.py", "old_content": "a"}, "y.py"),
        ("tools.file_delete", {"path": "z.py"}, "z.py"),
        ("tools.web_fetch", {"url": "https://e.example/x"}, "https://e.example/x"),
        ("tools.code_run", {"script": "echo hi\nrm -rf /"}, "echo hi"),  # 多行只取首行
        ("tools.delegate", {"task": "查资料"}, "查资料"),
        ("tools.gate_run", {"gate": "pytest"}, "pytest"),
        ("tools.context_read", {"pointer": "L2/fact"}, "L2/fact"),
        ("tools.unknown", {"path": "nope"}, ""),  # 白名单表外工具
        ("tools.file_read", {}, ""),  # 缺字段
        ("tools.file_read", {"path": "   "}, ""),  # 空白值
        ("tools.file_read", {"path": 42}, ""),  # 非字符串值
        ("tools.file_read", "path=src/a.py", ""),  # 事件面「超长节选」的 str 形态 ⇒ 不解析 repr
    ]
    for tool_id, args, expected in cases:
        assert _tool_target(tool_id, args) == expected, (tool_id, args)


def test_tool_target_truncates_long_value() -> None:
    """超长目标按有界长度截断并加省略号。"""
    assert _tool_target("tools.file_read", {"path": "p" * 200}) == "p" * _MAX_TARGET_CHARS + "…"


def test_action_title_paren_form() -> None:
    """工具步骤块标题：`Name(摘要)`；完成落 ` · 耗时` / ` · failed`；无摘要空括号。"""
    assert _action_title("Read", "src/a.py") == "Read(src/a.py)"
    assert _action_title("Read", "src/a.py", ok=True, ms=12) == "Read(src/a.py) · 12ms"
    assert _action_title("Read", "src/a.py", ok=False) == "Read(src/a.py) · failed"
    assert _action_title("Bash", "") == "Bash()"
    assert _action_title("Bash", "", ok=True, ms=1500) == "Bash() · 1.5s"
    assert _action_title("SubAgent", "查资料") == "SubAgent(查资料)"
    assert "⏺" not in _action_title("Bash", "echo hi")


def test_tui_step_block_expand_shows_full_text() -> None:
    """步骤块缺省**收起**；点标题展开 ⇒ **全文**（ui-scheme：无缩略中间态）。"""
    app = _step_app(_LONG_OUTPUT)

    async def drive() -> None:
        async with app.run_test(size=(100, 40)) as pilot:
            await _step_submit(pilot)
            from textual.widgets import Collapsible  # noqa: PLC0415

            block = _blocks(app)[0]
            assert block.collapsed is True  # 缺省收起
            title = block.query_one("CollapsibleTitle")
            assert await pilot.click(title)
            await pilot.pause()
            assert block.collapsed is False
            assert block.query_one(Collapsible.Contents).display is True
            body = str(_inner(block, ".step-body").render())
            assert len(body.split("\n")) == _LONG_LINES
            assert "第 1 行" in body and "第 20 行" in body

    asyncio.run(drive())


def test_tui_step_block_title_toggles_collapse() -> None:
    """点**标题** ⇒ 从收起展开；再点 ⇒ 收起。展开即全文。"""
    app = _step_app(_LONG_OUTPUT)

    async def drive() -> None:
        async with app.run_test(size=(100, 40)) as pilot:
            await _step_submit(pilot)
            from textual.widgets import Collapsible  # noqa: PLC0415 — 可选依赖懒 import

            block = _blocks(app)[0]
            title = block.query_one("CollapsibleTitle")
            assert block.collapsed is True
            assert block.query_one(Collapsible.Contents).display is False
            assert await pilot.click(title)
            await pilot.pause()
            assert block.collapsed is False
            assert block.query_one(Collapsible.Contents).display is True
            assert len(str(_inner(block, ".step-body").render()).split("\n")) == _LONG_LINES
            assert await pilot.click(title)
            await pilot.pause()
            assert block.collapsed is True
            assert block.query_one(Collapsible.Contents).display is False

    asyncio.run(drive())


def test_tui_spinner_hides_when_activity_block_appears() -> None:
    """活动块出现后、终态前：全局 spinner 已隐藏（ui-scheme：标题优先，spinner 兜底）。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())
    app = build_app(api)
    hold = asyncio.Event()

    class _HeldLoop:
        async def astream(self, user_input: str, *, session_id: str = ""):
            from core.loop import LoopEvent  # noqa: PLC0415

            yield LoopEvent("loop_started", {"trace_id": "t1"})
            yield LoopEvent(
                "action_started",
                {"round": 0, "tool_id": "tools.code_run", "args": {"script": "x"}},
            )
            await hold.wait()
            yield LoopEvent(
                "action_completed",
                {
                    "round": 0,
                    "tool_id": "tools.code_run",
                    "ok": True,
                    "duration_ms": 1,
                    "output": "ok",
                },
            )
            yield LoopEvent("loop_finished", {"reply": "done", "trace_id": "t1"})

    api._loop = _HeldLoop()  # noqa: SLF001

    async def drive() -> bool:
        async with app.run_test(size=(100, 40)) as pilot:
            from textual.widgets import Input, Static  # noqa: PLC0415

            inp = pilot.app.query_one("#input", Input)
            inp.focus()
            inp.value = "跑"
            await pilot.press("enter")
            for _ in range(40):
                await pilot.pause()
                if _blocks(app):
                    break
            shown = bool(app.query_one("#spinner", Static).display)
            hold.set()
            for _ in range(20):
                await pilot.pause()
            return shown

    assert asyncio.run(drive()) is False


def test_tui_step_block_body_wraps_wide_line() -> None:
    """展开后正文以**确定宽度**呈现 ⇒ 远超视口的单行**折行**而非被裁。"""
    app = _step_app("Z" * 200)

    async def drive() -> tuple[int, int, int]:
        async with app.run_test(size=(100, 40)) as pilot:
            from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import

            await _step_submit(pilot)
            block = _blocks(app)[0]
            title = block.query_one("CollapsibleTitle")
            assert await pilot.click(title)
            await pilot.pause()
            body = _inner(block, ".step-body")
            timeline = app.query_one("#timeline", Vertical)
            return body.size.width, body.virtual_size.width, timeline.size.width

    width, virtual, timeline_width = asyncio.run(drive())
    assert width <= timeline_width, (width, timeline_width)
    assert virtual <= timeline_width, (virtual, timeline_width)


def test_tui_step_block_shows_target_but_not_raw_args() -> None:
    """标题含**括号摘要**；**不含** ⏺、原始参数容器与内部 tool_id。"""
    app = _step_app("1", script="echo hi")

    async def drive() -> str:
        async with app.run_test(size=(100, 40)) as pilot:
            await _step_submit(pilot)
            return _timeline_text(app)

    text = asyncio.run(drive())
    assert "Shell(echo hi) · 12ms" in text
    assert "⏺" not in text
    assert "tools.code_run" not in text
    assert "{'script'" not in text


def test_tui_bash_title_keeps_script_when_args_long() -> None:
    """长 script 经 loop 节选后仍进 `Bash(...)` 括号（不因整包 str 截断变空壳）。"""
    from core.loop.default import _MAX_ACTION_EXCERPT, _args_excerpt  # noqa: PLC0415

    long_script = "echo " + "x" * (_MAX_ACTION_EXCERPT + 50)
    excerpt = _args_excerpt({"script": long_script})
    assert isinstance(excerpt, dict)
    assert "script" in excerpt
    # 标题取首行有界
    target = _tool_target("tools.code_run", excerpt)
    assert target.startswith("echo ")
    assert target.endswith("…")
    assert _action_title("Bash", target).startswith("Bash(echo ")


def test_tui_subagent_title_from_task_field() -> None:
    """SubAgent 括号摘要取 `task`；与 Bash 同源（结构化 args）。"""
    assert _tool_target("tools.delegate", {"task": "调研依赖"}) == "调研依赖"
    assert _action_title("SubAgent", "调研依赖") == "SubAgent(调研依赖)"
    long_task = "查" + "a" * 200
    from core.loop.default import _args_excerpt  # noqa: PLC0415

    excerpt = _args_excerpt({"task": long_task})
    target = _tool_target("tools.delegate", excerpt)
    assert target.startswith("查")
    assert "…" in target


def test_tui_thinking_stream_merges_and_updates_in_place() -> None:
    """同 round 思考增量归并同一块；缺省**收起**；标题不刷原文；展开可见全文。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())
    app = build_app(api)

    class _ThinkingLoop:
        async def astream(self, user_input: str, *, session_id: str = ""):
            from core.loop import LoopEvent  # noqa: PLC0415 — 事件构造

            yield LoopEvent("loop_started", {"trace_id": "t1"})
            yield LoopEvent("loop.reasoning", {"text": "先读文件", "round": 0})
            yield LoopEvent("loop.reasoning", {"text": "，再改配置", "round": 0})
            yield LoopEvent("reply_delta", {"text": "好了"})
            yield LoopEvent("loop_finished", {"reply": "好了", "trace_id": "t1"})

    api._loop = _ThinkingLoop()  # noqa: SLF001 — 注入替身驱动事件面

    async def drive() -> tuple[str, int, bool, str, str]:
        async with app.run_test(size=(100, 40)) as pilot:
            await _step_submit(pilot)
            blocks = _blocks(app)
            collapsed = [b.collapsed for b in blocks]
            titles = [str(b.title) for b in blocks]
            # 展开后才能在时间线文本里读到正文
            for b in blocks:
                title = b.query_one("CollapsibleTitle")
                assert await pilot.click(title)
                await pilot.pause()
            return _timeline_text(app), len(blocks), all(collapsed), str(app._last_reply), titles[0]

    text, blocks, all_collapsed, reply, title = asyncio.run(drive())
    assert blocks == 1, "同 round 思考增量归并到同一块（不逐段新建）"
    assert all_collapsed, "思考块缺省**收起**"
    assert title.startswith("Thinking · "), f"轮结束应带耗时后缀，得 {title!r}"
    assert "先读文件" not in title and "再改配置" not in title
    assert "Thinking" in text
    assert "先读文件，再改配置" in text
    assert reply == "好了"


def test_tui_thinking_title_stays_without_content_while_streaming() -> None:
    """收起态 Thinking 标题不刷思考原文（进行中可为 Thinking…）。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())
    app = build_app(api)

    class _LongThinking:
        async def astream(self, user_input: str, *, session_id: str = ""):
            from core.loop import LoopEvent  # noqa: PLC0415

            yield LoopEvent("loop.reasoning", {"text": "分析路径 A", "round": 0})
            yield LoopEvent("loop.reasoning", {"text": "再对比路径 B", "round": 0})
            # 故意不发 loop_finished，便于在进行中断言标题（run_loop 仍会结束）
            yield LoopEvent("loop_finished", {"reply": "ok", "trace_id": "t1"})

    api._loop = _LongThinking()  # noqa: SLF001

    async def drive() -> str:
        async with app.run_test(size=(100, 40)) as pilot:
            await _step_submit(pilot)
            blocks = _blocks(app)
            assert len(blocks) == 1
            return str(blocks[0].title)

    title = asyncio.run(drive())
    # 终态已 settle ⇒ 带耗时；进行中形态测点见下方 hold 用例
    assert title.startswith("Thinking"), title
    assert "分析路径" not in title
    assert "对比路径" not in title


def test_tui_thinking_settle_appends_duration() -> None:
    """Thinking 落静标题带耗时：`Thinking · 12ms` / `Thinking · 1.2s`（对齐工具块完成后缀）。"""
    from core.ui.repl import _thinking_title  # noqa: PLC0415

    assert _thinking_title(True) == "Thinking…"
    assert _thinking_title(False) == "Thinking"
    assert _thinking_title(False, ms=12) == "Thinking · 12ms"
    assert _thinking_title(False, ms=1500) == "Thinking · 1.5s"


def test_step_symbols_differ_by_kind() -> None:
    """活动块折叠符按种类区分（不再统一 ▶；ui-scheme 图标表）。"""
    from core.ui.repl import _step_symbol  # noqa: PLC0415

    assert _step_symbol("Thinking") == "✦"
    assert _step_symbol("Bash") == "$"
    assert _step_symbol("Read") == "◇"
    assert _step_symbol("WebFetch") == "◎"
    assert _step_symbol("SubAgent") == "⊕"
    assert len({_step_symbol(k) for k in ("Thinking", "Bash", "Read", "WebFetch", "SubAgent")}) == 5  # noqa: PLR2004 — 五类各异


def test_tui_thinking_and_bash_use_distinct_collapse_symbols() -> None:
    """时间线上 Thinking 与 Bash 的折叠符不相同。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())
    app = build_app(api)

    class _Mixed:
        async def astream(self, user_input: str, *, session_id: str = ""):
            from core.loop import LoopEvent  # noqa: PLC0415

            yield LoopEvent("loop.reasoning", {"text": "想", "round": 0})
            yield LoopEvent(
                "action_started",
                {"round": 0, "tool_id": "tools.code_run", "args": {"script": "echo"}},
            )
            yield LoopEvent(
                "action_completed",
                {
                    "round": 0,
                    "tool_id": "tools.code_run",
                    "ok": True,
                    "duration_ms": 1,
                    "output": "ok",
                },
            )
            yield LoopEvent("loop_finished", {"reply": "done", "trace_id": "t1"})

    api._loop = _Mixed()  # noqa: SLF001

    async def drive() -> tuple[str, str]:
        async with app.run_test(size=(100, 40)) as pilot:
            from textual.widgets._collapsible import CollapsibleTitle  # noqa: PLC0415

            await _step_submit(pilot)
            blocks = _blocks(app)
            assert len(blocks) == 2  # noqa: PLR2004
            t0 = blocks[0].query_one(CollapsibleTitle)
            t1 = blocks[1].query_one(CollapsibleTitle)
            return str(t0.collapsed_symbol), str(t1.collapsed_symbol)

    think_sym, bash_sym = asyncio.run(drive())
    assert think_sym == "✦"
    assert bash_sym == "$"
    assert think_sym != bash_sym


def test_tui_thinking_splits_by_round() -> None:
    """不同 round 的思考各自成块（均缺省收起）。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())
    app = build_app(api)

    class _TwoRoundThinking:
        async def astream(self, user_input: str, *, session_id: str = ""):
            from core.loop import LoopEvent  # noqa: PLC0415

            yield LoopEvent("loop.reasoning", {"text": "步一", "round": 0})
            yield LoopEvent("loop.reasoning", {"text": "步二", "round": 1})
            yield LoopEvent("loop_finished", {"reply": "ok", "trace_id": "t1"})

    api._loop = _TwoRoundThinking()  # noqa: SLF001

    async def drive() -> int:
        async with app.run_test(size=(100, 40)) as pilot:
            await _step_submit(pilot)
            return len(_blocks(app))

    assert asyncio.run(drive()) == 2  # noqa: PLR2004 — 两步各一块


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
    assert "验收：给出来源\nShell()\nShell() · 1.5s\n· 第 1 轮完成\n判定：验收通过\n答案 42" in text
    assert "tools.code_run" not in text  # 内部 tool_id 不进用户可见层
    assert "print(1)" not in text  # 原始参数不进用户可见层（白名单字段是 script 非 code）


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
    assert running.startswith("子任务 1")  # 主题（goal）与 sid 仍在；无 ▸
    assert done == "子任务 1  ✓ 查资料"


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
    assert text.count("Read()") == 1  # 未知 id（9）的里程碑被忽略；已知 id（1）的呈现一次
    assert "Read() · 12ms" in text
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
    assert "验收：给出来源\nRead() · 12ms" in text
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
    assert "子任务 1" in focused  # 主题（sid + goal）沿用折叠块口径；无 ▸
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
    assert "Shell() · 1.5s" in mid  # 里程碑：友好名 + 耗时（复用动作行口径）
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
    assert "Shell" in panel  # 友好名（未注入平台事实 ⇒ 中性名）
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
        "/resume",
        "/doctor",
        "/status",
        "/sessions",
        "/config",
        "/mcp",
        "/skill",
        "/notes",
        "/chain",
    ]


def test_palette_options_filters_by_command_prefix() -> None:
    """候选按前缀收窄（只认命令名前缀）。"""
    assert [c.fill for c in _palette_options("/ta")] == ["/task"]
    assert [c.fill for c in _palette_options("/re")] == ["/recall", "/resume"]


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
    assert by_fill["/resume"].arg_next is True
    assert by_fill["/main"].arg_next is False


def test_palette_options_second_level_lists_sessions() -> None:
    """`/resume` 的二级候选取**既有会话面**（显示行 + 标识），且**只**吃会话面。"""
    sessions = (("s-alpha", "部署脚本 · s-alpha"), ("s-beta", "重构计划 · s-beta"))
    cands = _palette_options("/resume ", subtask_ids=["1"], sessions=sessions)
    assert [c.fill for c in cands] == ["/resume s-alpha", "/resume s-beta"]
    assert [c.label for c in cands] == ["部署脚本 · s-alpha", "重构计划 · s-beta"]


def test_palette_options_session_narrows_by_label_or_id() -> None:
    """会话候选按**显示行前缀**（大小写不敏感）或**标识前缀**（逐字）收窄（标题可读、标识可粘）。"""
    sessions = (("s-alpha", "部署脚本 · s-alpha"), ("s-beta", "重构计划 · s-beta"))
    assert [c.fill for c in _palette_options("/resume 重构", sessions=sessions)] == [
        "/resume s-beta"
    ]
    assert [c.fill for c in _palette_options("/resume s-a", sessions=sessions)] == [
        "/resume s-alpha"
    ]
    assert [c.fill for c in _palette_options("/resume zzz", sessions=sessions)] == []


def _palette_api(
    *, orchestrator: object | None = None, diagnostics: Deps | None = None
) -> tuple[UIAPILayer, RecordingLoop]:
    """浮层用例的 api：真 `RecordingLoop` + 可选编排器桩 / 只读诊断源（LLM 已配置）。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop, orchestrator=orchestrator, diagnostics=diagnostics)
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
    """输入 `/` ⇒ 浮层可见并列出单一真源内的全部命令（顺序即真源顺序）。"""
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
        "cmd:/resume",
        "cmd:/doctor",
        "cmd:/status",
        "cmd:/sessions",
        "cmd:/config",
        "cmd:/mcp",
        "cmd:/skill",
        "cmd:/notes",
        "cmd:/chain",
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

    任一条只登记、未接线（如登记后忘了接分发）本用例即红 —— 故 0159 刻意不把 `/resume`
    放进真源，直到 0160 把「会话切换」接上；0163 新增的 7 条只读命令同受此守护。
    """
    orch = _TaskOrchestrator([("task_finished", {"outcomes": []})])
    api, loop = _palette_api(orchestrator=orch)
    sid = api.create_session("cli")  # `/resume` 需一个已登记会话
    app = build_app(api)

    async def drive() -> None:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            for line in (
                "/task 目标",
                "/focus 1",
                "/main",
                "/summon qinglong",
                "/recall qinglong",
                f"/resume {sid}",
                "/doctor",
                "/status",
                "/sessions",
                "/config",
                "/mcp",
                "/skill",
                "/notes",
            ):
                inp.value = line
                await pilot.press("enter")
                for _ in range(30):
                    await pilot.pause()

    asyncio.run(drive())
    assert loop.inputs == []  # 全部被分发链消费（无一落进普通对话）


# ---- 会话切换（`/resume`，change 0160 / ADR-0152） ----


def _switch_api(
    *, orchestrator: object | None = None
) -> tuple[UIAPILayer, RecordingLoop, str, str]:
    """两个已登记会话的 api：A（当前，空转录）与 B（含用户消息 + 带围栏的 agent 回复）。"""
    transcript = TranscriptStore()
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop, transcript=transcript, orchestrator=orchestrator)
    api.set_llm_config(_llm())
    a = api.create_session("cli")
    b = api.create_session("cli")
    transcript.append(b, "user", "B 的提问")
    transcript.append(b, "assistant", "B 的回答：\n\n```python\nprint(1)\n```\n")
    return api, loop, a, b


async def _timeline_view(app: object) -> tuple[list[str], list[str], int]:
    """`run_test` **内**的时间线快照：(Static 渲染文本, Markdown 源文本, MarkdownFence 数)。"""
    from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
    from textual.widgets import Markdown  # noqa: PLC0415 — 可选依赖懒 import

    static = [str(w.render()) for w in app.query("#timeline Static")]  # type: ignore[attr-defined]
    blocks = list(app.query_one("#timeline", Vertical).query(Markdown))  # type: ignore[attr-defined]
    fences = [type(k).__name__ for block in blocks for k in block.query("*")].count("MarkdownFence")
    return static, [str(block.source) for block in blocks], fences


def test_resume_switches_session_and_replays_markdown() -> None:
    """`/resume <B>`：时间线清空并铺入 B 的转录（agent 回复成 Markdown），后续轮次落 B。"""
    api, loop, a, b = _switch_api()
    app = build_app(api, a)

    async def drive() -> tuple[list[str], list[str], int, list[str]]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            await pilot.pause()
            inp.value = f"/resume {b}"
            await pilot.press("enter")
            for _ in range(10):
                await pilot.pause()
            static, markdown, fences = await _timeline_view(app)
            inp.value = "切换后的一轮"
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause()
            return static, markdown, fences, loop.sessions

    static, markdown, fences, sessions = asyncio.run(drive())
    assert any("续接会话" in line and b in line for line in static)  # 切换落痕
    assert any("B 的提问" in line for line in static)  # 用户消息按 ❯ 回显行
    assert markdown == ["B 的回答：\n\n```python\nprint(1)\n```\n"]  # agent 回复成 Markdown
    assert fences == 1  # 围栏成代码块（SHALL NOT 退化为明文）
    assert sessions[-1] == b  # 后续轮次落新会话


def test_resume_unknown_session_fails_closed_without_touching_state() -> None:
    """`/resume <未登记>`：不切换（时间线只多一行错误），后续轮次仍在原会话。"""
    api, loop, a, _b = _switch_api()
    app = build_app(api, a)

    async def drive() -> tuple[list[str], list[str], list[str]]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            await pilot.pause()
            before = (await _timeline_view(app))[0]
            inp.value = "/resume nope"
            await pilot.press("enter")
            for _ in range(10):
                await pilot.pause()
            after = (await _timeline_view(app))[0]
            inp.value = "仍然在 A"
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause()
            return before, after, loop.sessions

    before, after, sessions = asyncio.run(drive())
    assert after[: len(before)] == before  # 既有内容逐字不变
    assert len(after) == len(before) + 1  # 仅多一行错误
    assert after[-1].startswith("[UI_SESSION_NOT_FOUND]")  # fail-closed 的结构化错误
    assert sessions[-1] == a  # 未切换


def test_resume_without_arg_prints_usage_only() -> None:
    """`/resume` 无参数：只提示用法、不切换、不改动时间线（仅多一行提示）。"""
    api, loop, a, _b = _switch_api()
    app = build_app(api, a)

    async def drive() -> tuple[list[str], list[str]]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            await pilot.pause()
            before = (await _timeline_view(app))[0]
            inp.value = "/resume"
            await pilot.press("enter")
            for _ in range(10):
                await pilot.pause()
            after = (await _timeline_view(app))[0]
            inp.value = "仍在 A"
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause()
            return before, after

    before, after = asyncio.run(drive())
    assert after[: len(before)] == before
    assert after[-1] == "用法：/resume <会话标识>"
    assert loop.sessions[-1] == a  # 未切换


def test_resume_rejected_while_busy() -> None:
    """本轮执行未结束 ⇒ 拒绝切换（与既有忙态互斥同口径），当前会话不变。"""
    milestone, done = asyncio.Event(), asyncio.Event()
    orch = _GatedOrchestrator(milestone=milestone, done=done)
    api, _loop, a, b = _switch_api(orchestrator=orch)
    app = build_app(api, a)

    async def drive() -> list[str]:
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            await _type_line(pilot, "/task 查答案")
            await _wait_started(pilot, orch)
            inp.value = f"/resume {b}"
            await pilot.press("enter")
            for _ in range(5):
                await pilot.pause()
            after = (await _timeline_view(app))[0]
            milestone.set()
            done.set()
            for _ in range(20):
                await pilot.pause()
            return after

    after = asyncio.run(drive())
    assert any("处理中" in line for line in after)  # 忙碌拒绝
    assert not any("续接会话" in line for line in after)  # 未切换


def test_resume_resets_previous_session_view_state() -> None:
    """切换后复位呈现态：子任务折叠块句柄清空、焦点视图回主视图（无悬挂 widget）。"""
    orch = _TaskOrchestrator(
        [
            ("task_started", {"task_id": "t1", "goal": "复合目标"}),
            (
                "subtask_started",
                {"task_id": "t1", "subtask_id": "1", "goal": "查资料", "acceptance": "给出来源"},
            ),
            ("subtask_completed", {"task_id": "t1", "subtask_id": "1", "ok": True}),
            ("task_finished", {"outcomes": []}),
        ]
    )
    api, _loop, a, b = _switch_api(orchestrator=orch)
    app = build_app(api, a)

    async def drive() -> tuple[bool, dict[str, object], bool, bool]:
        from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            await _type_line(pilot, "/task 查答案")
            for _ in range(30):
                await pilot.pause()
            inp.value = "/focus 1"
            await pilot.press("enter")
            await pilot.pause()
            focused = bool(app.query_one("#panel", Vertical).display)
            inp.value = f"/resume {b}"
            await pilot.press("enter")
            for _ in range(10):
                await pilot.pause()
            return (
                focused,
                dict(app._open),  # noqa: SLF001 — 断言跨会话句柄已清
                bool(app.query_one("#panel", Vertical).display),
                bool(app.query_one("#timeline", Vertical).display),
            )

    focused, opened, panel_visible, timeline_visible = asyncio.run(drive())
    assert focused is True  # 前置：切换前确实在焦点视图
    assert opened == {}  # 子任务句柄已清（旧 widget 已随时间线销毁）
    assert panel_visible is False
    assert timeline_visible is True


def test_registry_handlers_resolve() -> None:
    """每条真源登记项的 `handler` 都能在 app 上**解析得到**（登记名笔误即红）。"""
    api, _ = _palette_api()
    app = build_app(api)

    async def drive() -> list[str]:
        async with app.run_test():
            return [
                cmd.handler
                for cmd in _COMMANDS
                if cmd.handler and not callable(getattr(app, cmd.handler, None))
            ]

    assert asyncio.run(drive()) == []


# ---- TUI 只读命令族（change 0163 / ADR-0154） ----

_READONLY_KINDS = (
    "/doctor",
    "/status",
    "/sessions",
    "/config",
    "/mcp",
    "/skill",
    "/notes",
    "/chain",
)
_READONLY_CANARY = "sk-READONLY-CANARY-7c21"
_READONLY_YAML = """\
llm:
  provider: deepseek
  model: deepseek-chat
  endpoint: https://api.deepseek.com/v1
  api_key: ${CORE_READONLY_KEY}
"""


def _readonly_deps(
    tmp_path: object, *, chain: Callable[[str], list[ChainNode]] | None = None
) -> Deps:
    """只读诊断源：密钥引用**可解析**，其值为哨兵（泄漏断言的靶子）。"""
    from pathlib import Path  # noqa: PLC0415 — 路径拼接随用例落 tmp_path

    root = Path(str(tmp_path))
    yaml_path = root / "config.yaml"
    yaml_path.write_text(_READONLY_YAML, encoding="utf-8")
    config = ConfigManager(yaml_path, environ={"CORE_READONLY_KEY": _READONLY_CANARY})
    return Deps(config=config, state_dir=root, chain=chain)


async def _submit(app: object, line: str) -> list[str]:
    """`run_test` 内提交一行，返回该行**新增**的时间线文本行。"""
    from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

    inp = app.query_one("#input", Input)  # type: ignore[attr-defined]
    inp.focus()
    before, _, _ = await _timeline_view(app)
    inp.value = line
    await app._pilot.press("enter")  # type: ignore[attr-defined]  # noqa: SLF001
    for _ in range(10):
        await app._pilot.pause()  # type: ignore[attr-defined]  # noqa: SLF001
    after, _, _ = await _timeline_view(app)
    return after[len(before) :]


def test_readonly_commands_render_result_block_without_touching_conversation(tmp_path) -> None:
    """8 条只读命令：各落结果块、**无** `❯` 回显、**零**对话轮次（承规格三 Scenario）。"""
    api, loop = _palette_api(diagnostics=_readonly_deps(tmp_path))
    app = build_app(api)

    async def drive() -> list[list[str]]:
        async with app.run_test() as pilot:
            app._pilot = pilot  # noqa: SLF001 — 供 `_submit` 取 pilot
            return [await _submit(app, kind) for kind in _READONLY_KINDS]

    blocks = asyncio.run(drive())
    for kind, block in zip(_READONLY_KINDS, blocks, strict=True):
        assert block, f"{kind} 未落结果块"
        assert not any("❯" in line for line in block), f"{kind} 落了用户输入回显"
    assert loop.inputs == []  # 无一进普通对话
    assert loop.sessions == []


def test_chain_command_renders_failure_marker(tmp_path) -> None:
    """`/chain`：注入链句柄 ⇒ 时间线呈现**失败标记**与 `after` 值（同 CLI 诊断面同一产出）。"""
    chain = {"": [ChainNode("loop.failure.t2", "t2", 2.0, True, "t1")]}
    api, loop = _palette_api(
        diagnostics=_readonly_deps(tmp_path, chain=lambda sid: chain.get(sid, []))
    )
    app = build_app(api)

    async def drive() -> list[str]:
        async with app.run_test() as pilot:
            app._pilot = pilot  # noqa: SLF001 — 供 `_submit` 取 pilot
            return await _submit(app, "/chain")

    block = asyncio.run(drive())
    assert any("失败" in line and "t1" in line for line in block), block
    assert loop.inputs == []


def test_readonly_commands_leak_no_secret(tmp_path) -> None:
    """`/config` 与 `/doctor`：只出现引用名，**逐字不含**密钥值（承规格 Scenario）。"""
    api, _ = _palette_api(diagnostics=_readonly_deps(tmp_path))
    app = build_app(api)

    async def drive() -> str:
        async with app.run_test() as pilot:
            app._pilot = pilot  # noqa: SLF001
            for kind in ("/config", "/doctor"):
                await _submit(app, kind)
            statics, _, _ = await _timeline_view(app)
            return "\n".join(statics)

    text = asyncio.run(drive())
    assert "${CORE_READONLY_KEY}" in text  # 引用名在场（正面证据）
    assert _READONLY_CANARY not in text  # 值不在场（红线）


def test_readonly_command_with_arg_prints_hint_only(tmp_path) -> None:
    """带参数 ⇒ 只提示、不执行（无结果块、不进对话）。"""
    api, loop = _palette_api(diagnostics=_readonly_deps(tmp_path))
    app = build_app(api)

    async def drive() -> list[str]:
        async with app.run_test() as pilot:
            app._pilot = pilot  # noqa: SLF001
            return await _submit(app, "/doctor 额外参数")

    extra = asyncio.run(drive())
    assert any("不接受参数" in line for line in extra)
    assert not any("自检诊断" in line for line in extra)  # 未执行
    assert loop.inputs == []


def test_readonly_command_rejected_while_busy(tmp_path) -> None:
    """忙碌中提交 `/doctor`：拒绝（提示处理中）、**零**结果块、**零**对话轮次。"""
    started = asyncio.Event()
    release = asyncio.Event()

    class _BlockingOrchestrator:
        """阻塞式编排器：`started` 后挂起，`release` 才收尾（忙态窗口确定）。"""

        async def astream(self, task_id: str, goal: str, **kwargs: object):
            started.set()
            await release.wait()
            yield LoopEvent("task_finished", {"outcomes": []})

    loop = RecordingLoop()
    api = UIAPILayer(
        loop=loop, orchestrator=_BlockingOrchestrator(), diagnostics=_readonly_deps(tmp_path)
    )
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> list[str]:
        from textual.widgets import Input  # noqa: PLC0415

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            for ch in "/task slow":
                await pilot.press(ch)
            await pilot.press("enter")
            for _ in range(50):
                await pilot.pause()
                if started.is_set():
                    break
            before, _, _ = await _timeline_view(app)
            inp.value = "/doctor"
            await pilot.press("enter")
            for _ in range(10):
                await pilot.pause()
            after, _, _ = await _timeline_view(app)
            release.set()  # 放行收尾
            for _ in range(20):
                await pilot.pause()
            return after[len(before) :]

    extra = asyncio.run(drive())
    assert any("处理中" in line for line in extra)  # 拒绝提示
    assert not any("自检诊断" in line for line in extra)  # 未落结果块
    assert loop.inputs == []


def test_readonly_commands_have_zero_side_effects(tmp_path) -> None:
    """零副作用：会话标识 / 会话数 / 转录条数**逐字不变**，时间线除新增块外**逐字不变**。"""
    root = tmp_path
    transcript = TranscriptStore(root / "messages.jsonl")
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop, transcript=transcript, diagnostics=_readonly_deps(tmp_path))
    api.set_llm_config(_llm())
    sid = api.create_session("cli")
    seeded = (("user", "早前的问题"), ("assistant", "早前的回答"))
    for role, body in seeded:
        transcript.append(sid, role, body)
    app = build_app(api, sid)

    async def drive() -> tuple[object, ...]:
        async with app.run_test() as pilot:
            app._pilot = pilot  # noqa: SLF001 — 供 `_submit` 取 pilot
            await _submit(app, "普通问题")  # 先攒出既有内容（含一轮对话）
            before = await _timeline_view(app)
            messages_before = len(transcript.read(sid))
            await _submit(app, "/status")
            after = await _timeline_view(app)
            return (
                before,
                after,
                messages_before,
                len(transcript.read(sid)),
                app._session_id,  # noqa: SLF001 — 呈现态真值即实例字段
                len(api.list_sessions()),
            )

    before, after, messages_before, messages, sid_after, sessions = asyncio.run(drive())
    before_static, before_md, before_fences = before
    after_static, after_md, after_fences = after
    assert after_static[: len(before_static)] == before_static, "既有时间线文本被改写"
    assert after_md[: len(before_md)] == before_md, "既有 Markdown 块被改写"
    assert after_fences == before_fences  # 围栏数（呈现态）不变
    assert len(after_static) == len(before_static) + 1  # 恰好**多一条**结果块
    assert sid_after == sid
    assert sessions == 1
    assert messages == messages_before == len(seeded)  # 仅预置的几条；只读命令**不**写转录


# ---- TUI 折叠呈现未能解析的模型原始输出（change 0170 / ADR-0161 / 台账 E107）----

_RAW_OUTPUT = (
    "清理状态确认：垃圾笔记已清零。\n\n现在立提案：\n\n"
    '{"tool_id": "tools.file_write", "args": {"path": "a.md", "content": "未写完'
)


def _raw_app(raw: str) -> object:
    """构造 app 并注入「一轮以不可解析收尾」的 loop 替身（`raw_output` 由调用方给定）。"""
    loop = RecordingLoop()
    api = UIAPILayer(loop=loop)
    api.set_llm_config(_llm())
    app = build_app(api)

    class _RawLoop:
        async def astream(self, user_input: str, *, session_id: str = ""):
            from core.loop import LoopEvent  # noqa: PLC0415 — 事件构造

            yield LoopEvent("loop_started", {"trace_id": "t1"})
            note = "LLM_PLAN_PARSE_FAILED: 疑似工具调用 JSON 未闭合"
            yield LoopEvent("reply_delta", {"text": note})
            yield LoopEvent(
                "loop_finished",
                LoopResult(
                    reply="LLM_PLAN_PARSE_FAILED: 疑似工具调用 JSON 未闭合",
                    trace_id="t1",
                    failed=True,
                    raw_output=raw,
                ),
            )

    api._loop = _RawLoop()  # noqa: SLF001 — 注入替身驱动事件面
    return app


def test_tui_raw_output_renders_collapsed_block() -> None:
    """不可解析收尾 ⇒ 一个**缺省收起**的步骤块；展开后正文含原始产出，正文不含原始 JSON。"""
    app = _raw_app(_RAW_OUTPUT)

    async def drive() -> tuple[bool, str, str]:
        from textual.widgets import Collapsible, Static  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test(size=(100, 40)) as pilot:
            await _step_submit(pilot)
            blocks = _blocks(app)
            assert len(blocks) == 1  # 恰好一个块（不并入正文）
            block = blocks[0]
            collapsed = bool(block.collapsed)
            # 展开前：正文藏于折叠区
            assert block.query_one(Collapsible.Contents).display is False
            assert await pilot.click(block.query_one("CollapsibleTitle"))
            await pilot.pause()
            body = str(block.query_one(".step-body", Static).render())
            from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import

            timeline = app.query_one("#timeline", Vertical)
            plain = "\n".join(
                str(w.render()) for w in timeline.query(Static) if not w.has_class("step-body")
            )
            return collapsed, body, plain

    collapsed, body, timeline_text = asyncio.run(drive())
    assert collapsed is True  # 缺省收起（不遮蔽时间线）
    assert "tools.file_write" in body  # 展开可见原始产出
    assert '"tool_id"' not in timeline_text  # 正文（块外）不含原始 JSON


def test_tui_no_raw_output_block_on_normal_turn() -> None:
    """正常轮（`raw_output` 为空）⇒ SHALL NOT 新增块（与既有行为逐字一致）。"""
    app = _raw_app("")

    async def drive() -> int:
        async with app.run_test(size=(100, 40)) as pilot:
            await _step_submit(pilot)
            return len(_blocks(app))

    assert asyncio.run(drive()) == 0


# ---- TUI 主/子 Agent 标签栏（change 0294 / ADR-0284） ----


def _tab_labels(app: object) -> list[str]:
    """标签栏文本（按渲染顺序；`main` 恒在首位）。"""
    return [str(w.render()) for w in app.query(".task-tab")]  # type: ignore[attr-defined]


class _SnapThenResetOrchestrator:
    """第一次任务：开工后挂起，收尾后保留快照；第二次任务：`task_started` 后挂起（可观察重置）。"""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.done = asyncio.Event()
        self.second_started = asyncio.Event()
        self.release = asyncio.Event()
        self._runs = 0

    async def astream(self, task_id: str, goal: str, **kwargs: object):
        self._runs += 1
        if self._runs == 1:
            yield LoopEvent("task_started", {"task_id": task_id, "goal": goal})
            yield LoopEvent(
                "subtask_started",
                {
                    "task_id": task_id,
                    "subtask_id": "1",
                    "goal": "查资料",
                    "acceptance": "给出来源",
                },
            )
            self.started.set()
            await self.done.wait()
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
            return
        yield LoopEvent("task_started", {"task_id": task_id, "goal": goal})
        self.second_started.set()
        await self.release.wait()
        yield LoopEvent("task_finished", {"outcomes": []})


def test_task_tabs_appear_and_switch_views() -> None:
    """标签自动出现（main + 主题缩写）；点击子任务/`main` 切换且主时间线逐字不变。"""
    milestone, done = asyncio.Event(), asyncio.Event()
    orch = _GatedOrchestrator(milestone=milestone, done=done)
    api = UIAPILayer(loop=RecordingLoop(), orchestrator=orch)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> tuple[list[str], bool, bool, bool, bool, str, str]:
        from textual.containers import Horizontal, Vertical  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            await _type_line(pilot, "/task 查答案")
            await _wait_started(pilot, orch)
            for _ in range(5):
                await pilot.pause()
            labels = _tab_labels(app)
            bar_shown = app.query_one("#task-tabs", Horizontal).display is True
            before = _timeline_text(app)
            sub_tab = next(w for w in app.query(".task-tab") if w.sid == "1")  # type: ignore[attr-defined]
            assert await pilot.click(sub_tab)
            for _ in range(5):
                await pilot.pause()
            panel_shown = app.query_one("#panel", Vertical).display is True
            timeline_hidden = app.query_one("#timeline", Vertical).display is False
            main_tab = next(w for w in app.query(".task-tab") if w.sid == "")  # type: ignore[attr-defined]
            assert await pilot.click(main_tab)
            for _ in range(5):
                await pilot.pause()
            timeline_back = app.query_one("#timeline", Vertical).display is True
            after = _timeline_text(app)
            milestone.set()
            done.set()
            for _ in range(20):
                await pilot.pause()
            return labels, bar_shown, panel_shown, timeline_hidden, timeline_back, before, after

    labels, bar_shown, panel_shown, timeline_hidden, timeline_back, before, after = asyncio.run(
        drive()
    )
    assert labels[0] == "main"
    assert any("查资料" in label for label in labels)
    assert bar_shown is True
    assert panel_shown is True
    assert timeline_hidden is True
    assert timeline_back is True
    assert after == before  # 切换是呈现层操作：零时间线写入


def test_clicking_subtask_block_title_focuses_and_still_toggles() -> None:
    """点击子任务折叠块标题 ⇒ 进入焦点视图，且既有展开/收起语义保持不变。"""
    milestone, done = asyncio.Event(), asyncio.Event()
    orch = _GatedOrchestrator(milestone=milestone, done=done)
    api = UIAPILayer(loop=RecordingLoop(), orchestrator=orch)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> tuple[bool, bool, bool]:
        from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            await _type_line(pilot, "/task 查答案")
            await _wait_started(pilot, orch)
            for _ in range(5):
                await pilot.pause()
            block = _blocks(app)[0]
            assert block.collapsed is True
            assert await pilot.click(block.query_one("CollapsibleTitle"))
            for _ in range(5):
                await pilot.pause()
            return (
                app.query_one("#panel", Vertical).display is True,
                app.query_one("#timeline", Vertical).display is False,
                bool(block.collapsed),
            )

    panel_shown, timeline_hidden, collapsed = asyncio.run(drive())
    assert panel_shown is True
    assert timeline_hidden is True
    assert collapsed is False  # 标题点击的展开语义未被拦截


def test_task_tabs_keep_terminal_snapshot_then_reset_on_next_task() -> None:
    """收尾保留 ✓ 标签与焦点；下一次 `task_started` 重置为仅 `main` 并回主视图。"""
    orch = _SnapThenResetOrchestrator()
    api = UIAPILayer(loop=RecordingLoop(), orchestrator=orch)
    api.set_llm_config(_llm())
    app = build_app(api)

    async def drive() -> tuple[list[str], bool, bool, list[str], bool, bool]:
        from textual.containers import Vertical  # noqa: PLC0415 — 可选依赖懒 import
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            await _type_line(pilot, "/task 查答案")
            await _wait_started(pilot, orch)
            for _ in range(5):
                await pilot.pause()
            sub_tab = next(w for w in app.query(".task-tab") if w.sid == "1")  # type: ignore[attr-defined]
            assert await pilot.click(sub_tab)
            for _ in range(5):
                await pilot.pause()
            orch.done.set()
            for _ in range(20):
                await pilot.pause()
            labels_after_finish = _tab_labels(app)
            focus_kept = app.query_one("#panel", Vertical).display is True
            timeline_hidden = app.query_one("#timeline", Vertical).display is False

            inp.focus()
            await _type_line(pilot, "/task 第二个目标")
            for _ in range(30):
                await pilot.pause()
                if orch.second_started.is_set():
                    break
            labels_reset = _tab_labels(app)
            panel_reset = app.query_one("#panel", Vertical).display is False
            timeline_back = app.query_one("#timeline", Vertical).display is True
            orch.release.set()
            for _ in range(10):
                await pilot.pause()
            return (
                labels_after_finish,
                focus_kept,
                timeline_hidden,
                labels_reset,
                panel_reset,
                timeline_back,
            )

    labels_after_finish, focus_kept, timeline_hidden, labels_reset, panel_reset, timeline_back = (
        asyncio.run(drive())
    )
    assert any("✓" in label and "查资料" in label for label in labels_after_finish)
    assert focus_kept is True  # 收尾不强制切回主视图
    assert timeline_hidden is True
    assert labels_reset == ["main"]  # 下一次 task_started：仅 main
    assert panel_reset is True
    assert timeline_back is True


def test_resume_clears_task_tabs() -> None:
    """`/resume` 切换会话 ⇒ 标签栏隐藏、标签模型清空、主视图恢复。"""
    orch = _TaskOrchestrator(
        [
            ("task_started", {"task_id": "t1", "goal": "复合目标"}),
            (
                "subtask_started",
                {"task_id": "t1", "subtask_id": "1", "goal": "查资料", "acceptance": "给出来源"},
            ),
            ("subtask_completed", {"task_id": "t1", "subtask_id": "1", "ok": True}),
            ("task_finished", {"outcomes": []}),
        ]
    )
    api, _loop, a, b = _switch_api(orchestrator=orch)
    app = build_app(api, a)

    async def drive() -> tuple[list[str], bool, bool, bool, bool]:
        from textual.containers import Horizontal, Vertical  # noqa: PLC0415 — 可选依赖懒 import
        from textual.widgets import Input  # noqa: PLC0415 — 可选依赖懒 import

        async with app.run_test() as pilot:
            inp = app.query_one("#input", Input)
            inp.focus()
            await _type_line(pilot, "/task 查答案")
            for _ in range(30):
                await pilot.pause()
            before = _tab_labels(app)
            inp.focus()
            inp.value = f"/resume {b}"
            await pilot.press("enter")
            for _ in range(10):
                await pilot.pause()
            return (
                before,
                app.query_one("#task-tabs", Horizontal).display is True,
                bool(app._task_tabs),  # noqa: SLF001 — 断言标签模型已清
                app.query_one("#panel", Vertical).display is True,
                app.query_one("#timeline", Vertical).display is True,
            )

    before, bar_shown, tabs_left, panel_shown, timeline_shown = asyncio.run(drive())
    assert any("查资料" in label for label in before)
    assert bar_shown is False
    assert tabs_left is False
    assert panel_shown is False
    assert timeline_shown is True


def test_tab_label_bounds_and_fallbacks() -> None:
    """主题缩写单行有界；空/空白 goal 回退 `子任务 <sid>`；markup 字符按字面呈现。"""
    from core.ui.repl import _tab_label  # noqa: PLC0415 — 被测纯函数

    long = _tab_label("查" * 50, "1")
    assert len(long) <= _TAB_MAX_CHARS
    assert long.endswith("…")
    assert "\n" not in _tab_label("第一行\n第二行", "2")
    assert _tab_label("   ", "3") == "子任务 3"
    assert _tab_label("", "4") == "子任务 4"
    assert "[red]" in _tab_label("[red]目标", "5")  # markup 不被解释
