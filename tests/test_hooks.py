"""钩子实现（change 0269）：事件面 / 阻断 / 只留痕 / 安全边界 / 配置面。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from core.configuration import ConfigManager
from core.hooks import (
    HOOK_EVENTS,
    HookEntry,
    HookEvent,
    HookManager,
    entries_from_config,
)
from core.loop import Action, ActionResult, DefaultLoop, LoopContext
from core.loop.protocol import current_trace_id
from core.memory import MemoryEntry, MemoryStore
from core.observability import TraceEvent, Tracer
from core.plugin_registry import CoeffectResolver
from core.runtime import build_runtime
from core.tools import Tool, ToolDef, ToolProvider

_VALID_YAML = """\
llm:
  provider: openai
  model: gpt-4o
  endpoint: https://api.openai.com/v1
  api_key: ${OPENAI_API_KEY}
"""


class _CapturingExporter:
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def emit(self, events: list[TraceEvent]) -> None:
        self.events.extend(events)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _manager(**kwargs: Any) -> HookManager:
    return HookManager(mode="test", **kwargs)


# ---- 事件面 / 摘要 / 脱敏 ----


def test_events_cover_the_contract() -> None:
    assert HOOK_EVENTS == (
        "session.start",
        "session.end",
        "turn.before",
        "turn.after",
        "tool.before",
        "tool.after",
        "memory.write",
    )


def test_tool_payload_is_digest_only_and_redacted() -> None:
    seen: list[HookEvent] = []
    hooks = _manager()
    hooks.register_callback("tool.before", lambda event: seen.append(event) or True)
    hooks.register_secret("literal-secret-value")

    allowed = _run(
        hooks.before_tool(
            "tools.echo",
            {"text": "sk-abcdefghijklmnop literal-secret-value"},
            "sess-1",
            "",
        )
    )

    assert allowed is True
    payload = seen[0].payload
    dumped = json.dumps(payload, ensure_ascii=False)
    assert "sk-abcdefghijklmnop" not in dumped
    assert "literal-secret-value" not in dumped
    assert payload["tool_id"] == "tools.echo"
    assert set(payload["args_digest"]) == {"chars", "hash"}


def test_after_payload_has_duration_and_digest() -> None:
    seen: list[HookEvent] = []
    hooks = _manager()
    hooks.register_callback("tool.after", lambda event: seen.append(event) or True)
    result = _result()

    _run(hooks.after_tool("tools.echo", result, "sess-1", ""))

    assert seen[0].payload["ok"] is True
    assert seen[0].payload["duration_ms"] == 7  # noqa: PLR2004
    assert set(seen[0].payload["result_digest"]) == {"chars", "hash"}


def _result() -> ActionResult:
    result = ActionResult(data={"value": "ok"})
    result.duration_ms = 7
    return result


# ---- before / after 失败语义 ----


def test_before_hook_nonzero_blocks() -> None:
    hooks = _manager(
        entries=[
            HookEntry(
                event="tool.before",
                command=(sys.executable, "-c", "raise SystemExit(3)"),
                timeout_s=5,
            )
        ]
    )
    assert _run(hooks.before_tool("tools.echo", {}, "s", "t")) is False


def test_after_hook_nonzero_only_logs() -> None:
    exporter = _CapturingExporter()
    tracer = Tracer(exporter=exporter)
    hooks = _manager(
        entries=[
            HookEntry(
                event="turn.after",
                command=(sys.executable, "-c", "raise SystemExit(9)"),
                timeout_s=5,
            )
        ],
        tracer=tracer,
    )
    trace_id = tracer.start_trace("turn")
    _run(hooks.after_turn("s", trace_id, True, 2))
    tracer.end_trace(trace_id)

    hook_events = [event for event in exporter.events if event.kind == "hook"]
    assert len(hook_events) == 1
    assert hook_events[0].payload["event"] == "turn.after"
    assert hook_events[0].payload["exit"] == 9  # noqa: PLR2004


def test_before_timeout_uses_on_error() -> None:
    slow = (sys.executable, "-c", "import time; time.sleep(3)")

    blocking = _manager(entries=[HookEntry(event="tool.before", command=slow, timeout_s=0.05)])
    assert _run(blocking.before_tool("tools.echo", {}, "s", "")) is False

    allowing = _manager(
        entries=[HookEntry(event="tool.before", command=slow, timeout_s=0.05, on_error="allow")]
    )
    assert _run(allowing.before_tool("tools.echo", {}, "s", "")) is True

    warning = _manager(
        entries=[HookEntry(event="tool.before", command=slow, timeout_s=0.05, on_error="warn")]
    )
    with pytest.warns(UserWarning):
        assert _run(warning.before_tool("tools.echo", {}, "s", "")) is True


def test_subprocess_does_not_inherit_secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOOK_SECRET", "should-not-leak")
    script = "import os,sys; sys.exit(1 if 'HOOK_SECRET' in os.environ else 0)"
    hooks = _manager(
        entries=[
            HookEntry(event="tool.before", command=(sys.executable, "-c", script), timeout_s=5)
        ]
    )
    assert _run(hooks.before_tool("tools.echo", {}, "s", "")) is True


def test_stdout_never_enters_trace() -> None:
    exporter = _CapturingExporter()
    tracer = Tracer(exporter=exporter)
    hooks = _manager(
        entries=[
            HookEntry(
                event="tool.after",
                command=(sys.executable, "-c", "print('CANARY-HOOK-OUTPUT')"),
                timeout_s=5,
            )
        ],
        tracer=tracer,
    )
    trace_id = tracer.start_trace("turn")
    _run(hooks.after_tool("tools.echo", _result(), "s", trace_id))
    tracer.end_trace(trace_id)

    assert "CANARY-HOOK-OUTPUT" not in json.dumps(
        [event.payload for event in exporter.events], ensure_ascii=False
    )


# ---- 配置面 ----


def _config_manager(
    tmp_path: Path, yaml: str, *, environ: dict[str, str] | None = None, cli=None
) -> ConfigManager:
    path = tmp_path / "config.yaml"
    path.write_text(yaml, encoding="utf-8")
    env = {"OPENAI_API_KEY": "sk-test", **(environ or {})}
    return ConfigManager(path, environ=env, cli=cli)


def test_yaml_block_sequence_is_parsed(tmp_path: Path) -> None:
    yaml = (
        _VALID_YAML
        + """\
hooks:
  enabled: true
  entries:
    - event: tool.before
      command: ["/bin/true"]
      match:
        tool_id: code_run
    - event: turn.after
      command: ["/bin/true"]
"""
    )
    manager = _config_manager(tmp_path, yaml)
    manager.load()

    entries = manager.hooks_entries()
    assert [entry["event"] for entry in entries] == ["tool.before", "turn.after"]
    assert entries[0]["command"] == ["/bin/true"]
    assert entries[0]["match"] == {"tool_id": "code_run"}


def test_hooks_scalar_priority_and_timeout_cap(tmp_path: Path) -> None:
    yaml = (
        _VALID_YAML
        + """\
hooks:
  enabled: true
  timeout_s: 3600
  on_error: warn
"""
    )
    manager = _config_manager(tmp_path, yaml, environ={"CORE_HOOKS_TIMEOUT_S": "9"})
    manager.load()

    assert manager.hooks_timeout_s() == 9  # noqa: PLR2004
    assert manager.hooks_on_error() == "warn"
    assert manager.hooks_enabled() is True

    cli = _config_manager(
        tmp_path,
        yaml,
        environ={"CORE_HOOKS_TIMEOUT_S": "9"},
        cli={"hooks.timeout_s": "7"},
    )
    cli.load()
    assert cli.hooks_timeout_s() == 7  # noqa: PLR2004

    tail = _config_manager(tmp_path, yaml)
    tail.load()
    with pytest.warns(UserWarning, match="60"):
        assert tail.hooks_timeout_s() == 60  # noqa: PLR2004


def test_entries_from_config_skips_invalid_items() -> None:
    with pytest.warns(UserWarning):
        entries = entries_from_config(
            [
                {"event": "not.an.event", "command": ["/bin/true"]},
                {"event": "tool.before", "command": "not-a-list"},
                {"event": "tool.before", "command": ["/bin/true"], "timeout_s": 3600},
            ],
            default_timeout_s=5,
            default_on_error="block",
        )
    assert len(entries) == 1
    assert entries[0].timeout_s == 60  # noqa: PLR2004


# ---- 循环接缝 ----


def _provider(calls: list[str]) -> ToolProvider:
    resolver = CoeffectResolver()
    provider = ToolProvider(coeffect_resolver=resolver)

    def handler(**args: Any) -> dict[str, Any]:
        calls.append("executed")
        return {"ok": True}

    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.echo",
                description="echo",
                schema={"type": "object"},
                coeffects=[],
                reversible=True,
            ),
            handler=handler,
        )
    )
    return provider


def _hook_middleware(hooks: HookManager):
    async def middleware(ctx: LoopContext, action: Action) -> Action | None:
        if action.is_terminal:
            return action
        allowed = await hooks.before_tool(
            action.tool_id, action.args, ctx.session_id, current_trace_id.get()
        )
        return action if allowed else None

    return middleware


def _hook_observer(hooks: HookManager):
    async def observer(ctx: LoopContext, action: Action, result: Any) -> None:
        await hooks.after_tool(action.tool_id, result, ctx.session_id, current_trace_id.get())

    return observer


def _turn_adapters(hooks: HookManager, seen: list[tuple[str, bool]]):
    async def before(session_id: str, trace_id: str, turn_index: int, text: str) -> bool:
        await hooks.start_session(session_id)
        return await hooks.before_turn(session_id, trace_id, turn_index, text)

    async def after(session_id: str, trace_id: str, ok: bool, steps: int) -> None:
        seen.append(("after", ok))
        await hooks.after_turn(session_id, trace_id, ok, steps)

    return before, after


def test_tool_before_hook_blocks_execution_and_traces_blocked_by() -> None:
    exporter = _CapturingExporter()
    tracer = Tracer(exporter=exporter)
    calls: list[str] = []
    hooks = _manager(tracer=tracer)
    hooks.register_callback("tool.before", lambda event: False)

    def planner(ctx: LoopContext) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={})
        return Action(args={"reply": "done"})

    loop = DefaultLoop(
        planner=planner,
        tools=_provider(calls),
        tracer=tracer,
        middlewares=[_hook_middleware(hooks)],
        max_rounds=3,
    )
    result = loop.run("q", session_id="sess-hook")

    assert calls == []
    assert result.reply.startswith("已拒绝")
    hook_events = [event for event in exporter.events if event.kind == "hook"]
    assert hook_events and hook_events[0].payload["blocked_by"] == "callback"


def test_tool_after_hook_receives_duration() -> None:
    hooks = _manager()
    seen: list[HookEvent] = []
    hooks.register_callback("tool.after", lambda event: seen.append(event) or True)
    calls: list[str] = []

    def planner(ctx: LoopContext) -> Action:
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={})
        return Action(args={"reply": "done"})

    loop = DefaultLoop(
        planner=planner,
        tools=_provider(calls),
        action_observers=[_hook_observer(hooks)],
        max_rounds=3,
    )
    loop.run("q", session_id="sess-hook")

    assert calls == ["executed"]
    assert seen and seen[0].name == "tool.after"
    assert isinstance(seen[0].payload["duration_ms"], int)


def test_turn_before_block_skips_planner_and_after_still_runs() -> None:
    hooks = _manager()
    hooks.register_callback("turn.before", lambda event: False)
    seen: list[tuple[str, bool]] = []
    before, after = _turn_adapters(hooks, seen)
    planner_calls: list[int] = []

    def planner(ctx: LoopContext) -> Action:
        planner_calls.append(ctx.rounds)
        return Action(args={"reply": "done"})

    loop = DefaultLoop(
        planner=planner,
        tools=_provider([]),
        turn_before=before,
        turn_after=after,
        max_rounds=3,
    )
    result = loop.run("q", session_id="sess-hook")

    assert planner_calls == []
    assert result.reply.startswith("已拒绝")
    assert seen == [("after", True)]


def test_session_events_are_idempotent() -> None:
    hooks = _manager()
    seen: list[str] = []
    hooks.register_callback("session.start", lambda event: seen.append("start") or True)
    hooks.register_callback("session.end", lambda event: seen.append("end") or True)

    _run(hooks.start_session("s"))
    _run(hooks.start_session("s"))
    hooks.close()
    hooks.close()

    assert seen == ["start", "end"]


# ---- memory.write ----


def test_memory_write_observer_cannot_veto_and_isolated_from_failure() -> None:
    seen: list[tuple[str, str, int]] = []
    store = MemoryStore(
        write_observer=lambda layer, entry: seen.append(
            (layer, entry.id, len(entry.content.encode()))
        )
    )
    entry = MemoryEntry(id="m1", layer="L2", content="hello", tags=[], source="loop", trace_id="t1")
    assert store.write("L2", entry) == "m1"
    assert seen == [("L2", "m1", 5)]

    def boom(layer: str, entry: MemoryEntry) -> None:
        raise RuntimeError("observer boom")  # noqa: TRY003 — 观察者失败探针

    failing = MemoryStore(write_observer=boom)
    entry2 = MemoryEntry(id="m2", layer="L2", content="ok", tags=[], source="loop", trace_id="t2")
    assert failing.write("L2", entry2) == "m2"


def test_memory_write_hook_payload_uses_entry_trace() -> None:
    exporter = _CapturingExporter()
    tracer = Tracer(exporter=exporter)
    hooks = _manager(tracer=tracer)
    seen: list[HookEvent] = []
    hooks.register_callback("memory.write", lambda event: seen.append(event) or True)
    store = MemoryStore(write_observer=lambda layer, entry: hooks.memory_write(layer, entry))

    entry = MemoryEntry(
        id="m9", layer="L2", content="hello", tags=[], source="loop", trace_id="trace-9"
    )
    trace_id = tracer.start_trace("memory")
    assert trace_id != "trace-9"  # 钩子痕归条目自己的 trace，不靠 ContextVar
    store.write("L2", entry)
    tracer.end_trace("trace-9")

    assert seen[0].payload == {"layer": "L2", "entry_id": "m9", "kind": "episodic", "bytes": 5}
    # 没有在途 trace-9 时，管理器开短命 trace ⇒ 事件仍导出
    assert [event.kind for event in exporter.events].count("hook") == 1


# ---- YAML round-trip / 组合根接线 ----


def test_yaml_roundtrip_preserves_hook_entries(tmp_path: Path) -> None:
    """`write_patch` 重 dump 后条目仍可解析（块序列 + flow 列表 + 嵌套映射对称）。"""
    yaml = (
        _VALID_YAML
        + """\
hooks:
  enabled: true
  entries:
    - event: tool.before
      command: ["/bin/true"]
      match:
        tool_id: code_run
"""
    )
    manager = _config_manager(tmp_path, yaml)
    manager.load()
    manager.write_patch({"llm": {"model": "gpt-4.1"}})
    manager.load()

    entries = manager.hooks_entries()
    assert entries[0]["event"] == "tool.before"
    assert entries[0]["command"] == ["/bin/true"]
    assert entries[0]["match"] == {"tool_id": "code_run"}


def test_runtime_wires_hooks_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """缺省关 ⇒ 不构造/不注入（逐字不变）；开启 ⇒ 主 loop 与记忆写面均接线。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME", str(tmp_path))

    off_path = tmp_path / "off.yaml"
    off_path.write_text(_VALID_YAML, encoding="utf-8")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state-off"))
    off = build_runtime(ConfigManager(yaml_path=off_path))
    assert off.loop._turn_before is None  # noqa: SLF001
    assert off.loop._turn_after is None  # noqa: SLF001
    assert off.memory._write_observer is None  # noqa: SLF001

    on_path = tmp_path / "on.yaml"
    on_path.write_text(
        _VALID_YAML
        + """\
hooks:
  enabled: true
  entries:
    - event: tool.before
      command: ["/bin/true"]
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state-on"))
    on = build_runtime(ConfigManager(yaml_path=on_path))
    assert on.loop._turn_before is not None  # noqa: SLF001
    assert on.loop._turn_after is not None  # noqa: SLF001
    assert on.memory._write_observer is not None  # noqa: SLF001


def test_turn_payload_redacts_registered_and_shaped_secrets() -> None:
    """turn 类载荷携带正文 ⇒ 脱敏必须真正生效（登记明文 + 正则形态）。"""
    seen: list[HookEvent] = []
    hooks = _manager()
    hooks.register_callback("turn.before", lambda event: seen.append(event) or True)
    hooks.register_secret("literal-secret-value")

    _run(hooks.before_turn("s", "t", 1, "use literal-secret-value and sk-abcdefghijklmnop"))

    dumped = json.dumps(seen[0].payload, ensure_ascii=False)
    assert "literal-secret-value" not in dumped
    assert "sk-abcdefghijklmnop" not in dumped
    assert "<redacted>" in dumped
