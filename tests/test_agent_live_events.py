"""前台委托实况事件（change 0298 / ADR-0288）。

覆盖三面：

* **loop 侧信道**：动作执行期工具写入的事件边执行边外发，且先于动作结果 / 终态；
  无订阅方（`arun`）零额外事件。
* **runtime 委托**：`tools.delegate` 前台路径产出 `agent.started → agent.progress →
  agent.completed`，进度字段按白名单裁剪；无订阅方仍走原 `arun`。
* **呈现辅助**：标题折叠/有界、回复节选有界。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest

from core.configuration import ConfigManager
from core.loop import (
    Action,
    DefaultLoop,
    LoopContext,
    LoopEvent,
    LoopResult,
    collect_result,
    current_event_sink,
)
from core.runtime import (
    _agent_reply_excerpt,
    _agent_title,
    _emit_agent_event,
    build_runtime,
)
from core.tools import Tool, ToolDef, ToolProvider

_REPLY_MAX = 4000  # 与 runtime._AGENT_REPLY_MAX 同口径

_VALID_YAML = """\
llm:
  provider: openai
  model: gpt-4o
  endpoint: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
"""


def _event_types(events: list[LoopEvent]) -> list[str]:
    return [event.type for event in events]


# ---- loop 侧信道 ----


def test_side_channel_events_are_yielded_before_action_result() -> None:
    """动作处理器写入的事件先于 `action_completed`，且不影响终态。"""

    def handler(text: str) -> str:
        sink = current_event_sink.get()
        assert sink is not None, "动作执行期必须可订阅侧信道"
        _emit_agent_event(
            sink,
            "agent.started",
            {"agent_id": "coding:x", "agent": "coding", "title": text},
        )
        return "ok"

    provider = ToolProvider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.spawn",
                description="spawn",
                schema={"type": "object", "properties": {"text": {"type": "string"}}},
                coeffects=[],
                reversible=True,
            ),
            handler=handler,
        )
    )

    def planner(ctx: LoopContext) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id="tools.spawn", args={"text": "写代码"})
        return Action(args={"reply": "完成"})

    loop = DefaultLoop(planner=planner, tools=provider)

    async def scenario() -> LoopResult:
        events: list[LoopEvent] = []
        result = await collect_result(loop.astream("任务"), on_event=events.append)
        types = _event_types(events)
        assert "agent.started" in types
        assert types.index("agent.started") < types.index("action_completed")
        assert types[-1] == "loop_finished"
        return result

    result = asyncio.run(scenario())
    assert result.reply == "完成"


def test_no_subscriber_keeps_event_stream_unchanged() -> None:
    """`arun`（无侧信道订阅）⇒ 事件里不出现 `agent.*`。"""

    provider = ToolProvider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.noop",
                description="noop",
                schema={"type": "object", "properties": {}},
                coeffects=[],
                reversible=True,
            ),
            handler=lambda: "ok",
        )
    )

    def planner(ctx: LoopContext) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id="tools.noop")
        return Action(args={"reply": "完成"})

    loop = DefaultLoop(planner=planner, tools=provider)

    async def scenario() -> list[str]:
        return [event.type async for event in loop.astream("任务")]

    types = asyncio.run(scenario())
    assert not [item for item in types if item.startswith("agent.")]


# ---- runtime 前台委托 ----


def _runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "home").mkdir(exist_ok=True)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(_VALID_YAML, encoding="utf-8")
    return build_runtime(ConfigManager(yaml_path=config_path))


def _coding_loop(runtime: Any) -> Any:
    return runtime.orchestrator._router._agents["coding"].loop  # noqa: SLF001


def test_foreground_delegate_emits_lifecycle_and_whitelisted_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    coding = _coding_loop(runtime)

    async def fake_stream(task: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        assert task == "写代码"
        assert session_id == ""
        yield LoopEvent("loop_started", {"trace_id": "t-sub"})
        yield LoopEvent(
            "action_started",
            {
                "round": 0,
                "tool_id": "tools.file_write",
                "args": {"path": "a.py"},
                "chain_of_thought": "不应外发",
            },
        )
        yield LoopEvent("thinking_delta", {"delta": "不应外发"})
        yield LoopEvent("loop_finished", LoopResult(reply="完成", trace_id="t-sub"))

    monkeypatch.setattr(coding, "astream", fake_stream)

    async def scenario() -> tuple[Any, list[LoopEvent]]:
        sink: asyncio.Queue[LoopEvent] = asyncio.Queue()
        token = current_event_sink.set(sink)
        try:
            result = await runtime.tools.ainvoke(
                "tools.delegate", {"task": "写代码"}, trace_id="t1"
            )
            events: list[LoopEvent] = []
            while not sink.empty():
                events.append(sink.get_nowait())
            return result, events

        finally:
            current_event_sink.reset(token)

    result, events = asyncio.run(scenario())

    assert result.ok is True
    assert cast(dict[str, Any], result.data)["reply"] == "完成"
    assert _event_types(events) == [
        "agent.started",
        "agent.progress",
        "agent.completed",
    ]
    started, progress, completed = (cast(dict[str, Any], event.payload) for event in events)
    assert started["agent"] == "coding"
    assert started["title"] == "写代码"
    assert cast(str, started["agent_id"]).startswith("coding:")
    assert progress["event"] == "action_started"
    assert progress["data"] == {
        "round": 0,
        "tool_id": "tools.file_write",
        "args": {"path": "a.py"},
    }
    assert completed["ok"] is True
    assert completed["reply"] == "完成"


def test_foreground_delegate_without_subscriber_uses_arun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无订阅方 ⇒ 原 `arun` 路径逐字保留（不强制改走事件流）。"""

    runtime = _runtime(tmp_path, monkeypatch)
    coding = _coding_loop(runtime)
    calls: list[str] = []

    async def fake_arun(task: str, *, session_id: str = "") -> LoopResult:  # noqa: ARG001
        calls.append(task)
        return LoopResult(reply="同步结果", trace_id="t-sub")

    async def fake_stream(task: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        raise AssertionError  # 无订阅方不得改走 astream
        yield LoopEvent("loop_started", {})  # pragma: no cover

    monkeypatch.setattr(coding, "arun", fake_arun)
    monkeypatch.setattr(coding, "astream", fake_stream)

    async def scenario() -> Any:
        assert current_event_sink.get() is None
        return await runtime.tools.ainvoke("tools.delegate", {"task": "写代码"}, trace_id="t1")

    result = asyncio.run(scenario())
    assert calls == ["写代码"]
    assert cast(dict[str, Any], result.data) == {"ok": True, "reply": "同步结果"}


def test_foreground_delegate_exception_emits_failed_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime(tmp_path, monkeypatch)
    coding = _coding_loop(runtime)

    async def fake_stream(task: str, *, session_id: str = "") -> AsyncIterator[LoopEvent]:
        raise RuntimeError("内部细节不应外泄")
        yield LoopEvent("loop_started", {})  # pragma: no cover

    monkeypatch.setattr(coding, "astream", fake_stream)

    async def scenario() -> tuple[Any, list[LoopEvent]]:
        sink: asyncio.Queue[LoopEvent] = asyncio.Queue()
        token = current_event_sink.set(sink)
        try:
            result = await runtime.tools.ainvoke(
                "tools.delegate", {"task": "写代码"}, trace_id="t1"
            )
            events: list[LoopEvent] = []
            while not sink.empty():
                events.append(sink.get_nowait())
            return result, events
        finally:
            current_event_sink.reset(token)

    result, events = asyncio.run(scenario())
    assert result.ok is False
    completed = cast(dict[str, Any], events[-1].payload)
    assert events[-1].type == "agent.completed"
    assert completed["ok"] is False
    assert "RuntimeError" in cast(str, completed["reply"])
    assert "内部细节" not in cast(str, completed["reply"])


# ---- 呈现辅助 ----


def test_agent_title_is_first_line_collapsed_and_bounded() -> None:
    assert _agent_title("\n  第一行   标题\n第二行") == "第一行 标题"
    assert _agent_title("长" * 80) == "长" * 59 + "…"
    assert _agent_title("   ") == ""


def test_agent_reply_excerpt_is_bounded() -> None:
    assert _agent_reply_excerpt("abc") == "abc"
    excerpt = _agent_reply_excerpt("x" * 5000)
    assert len(excerpt) == _REPLY_MAX
    assert excerpt.endswith("…")
