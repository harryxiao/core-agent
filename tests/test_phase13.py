"""Phase 13 系统级接线测试（M9 单 Agent 真闭环）。

覆盖：runtime 组合根装配 + coeffect 缺失拒绝启动；LLMPlanner 接 LLM（含解析失败
错误码）；热路径 TraceEvent 落点；PermissionGuard 不可逆审批 / 拒绝短路；
judgment 三决策点（loop choice / memory score / permission noul）注入断言；
entry 贯通装配。
"""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest

from core import entry
from core.configuration import ConfigManager, ConfigurationError
from core.context import DynamicAssembler
from core.judgment import DecisionPrimitive, DecisionResult
from core.llm_provider import LLMResponse, TokenUsage
from core.loop import Action, DefaultLoop, LLMPlanner, LoopContext
from core.memory import MemoryStore
from core.observability import Tracer
from core.permission import PermissionGuard
from core.runtime import build_runtime
from core.tools import Tool, ToolDef, ToolProvider


def _echo_tool() -> Tool:
    return Tool(
        definition=ToolDef(
            tool_id="tools.echo",
            description="echo",
            schema={"type": "object", "properties": {"text": {"type": "string"}}},
            coeffects=[],
            reversible=True,
        ),
        handler=lambda text: f"echo:{text}",
    )


class _FakeLLM:
    """记录 LLMRequest、返回固定 content 的假 LLM。"""

    def __init__(self, content: str) -> None:
        self._content = content
        self.requests: list[object] = []

    def completion(self, request: object) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(
            content=self._content,
            usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
            finish_reason="stop",
            provider="fake",
            model="test-model",
        )


def _write_config(tmp_path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n",
        encoding="utf-8",
    )
    return str(cfg)


# ---- runtime 组合根 ----


def test_build_runtime_assembles_all_deps(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert runtime.app.llm.model == "test-model"
    assert runtime.llm is not None
    assert runtime.memory is not None
    assert runtime.tools is not None
    assert runtime.tracer is not None
    assert runtime.router is not None
    assert runtime.loop is not None
    ids = {t.tool_id for t in runtime.tools.active_tools()}
    assert ids == {"tools.file_read", "tools.file_write", "tools.file_patch"}


def test_build_runtime_rejects_missing_config(tmp_path) -> None:
    with pytest.raises(ConfigurationError):
        build_runtime(ConfigManager(yaml_path=str(tmp_path / "missing.yaml")))


# ---- LLMPlanner 接 LLM ----


def test_llm_planner_returns_action_and_carries_context(tmp_path) -> None:
    provider = ToolProvider()
    provider.register(_echo_tool())
    fake = _FakeLLM('{"tool_id": "tools.echo", "args": {"text": "hi"}}')
    assembler = DynamicAssembler(constitution=["规则A"])
    planner = LLMPlanner(
        fake, assembler=assembler, skill_router=lambda task: ["skills.x.y"], tools=provider
    )

    action = planner(LoopContext(messages=[{"role": "user", "content": "hi"}]))

    assert action.tool_id == "tools.echo"
    assert action.args == {"text": "hi"}
    request = fake.requests[0]
    # 工具 schema 进 LLMRequest.tools；宪法/技能进 system prompt
    assert request.tools == [t.schema for t in provider.active_tools()]
    system = request.messages[0].content
    assert "规则A" in system
    assert "skills.x.y" in system


def test_llm_planner_parse_failure_error_code() -> None:
    planner = LLMPlanner(_FakeLLM('{"tool_id": "tools.echo",'))
    action = planner(LoopContext(messages=[{"role": "user", "content": "hi"}]))
    assert "LLM_PLAN_PARSE_FAILED" in action.args["reply"]


def test_llm_planner_plain_text_reply() -> None:
    planner = LLMPlanner(_FakeLLM("直接回复文本"))
    action = planner(LoopContext(messages=[{"role": "user", "content": "hi"}]))
    assert action.args == {"reply": "直接回复文本"}
    assert action.is_terminal


# ---- 热路径 TraceEvent ----


def test_loop_emits_trace_events() -> None:
    tracer = Tracer()
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "ok"}), tracer=tracer)
    result = loop.run("hi")
    kinds = {e.kind for e in tracer.replay(result.trace_id)}
    assert {"loop_started", "loop_finished"} <= kinds


# ---- PermissionGuard ----


def test_permission_guard_irreversible_requires_confirm() -> None:
    guard = PermissionGuard()
    decision = guard.confirm(
        "tools.file_write", {"path": "x"}, ["filesystem:write"], reversible=False
    )
    assert decision.action == "confirm"


def test_permission_guard_deny_short_circuits_loop() -> None:
    provider = ToolProvider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.file_write",
                description="write",
                schema={"type": "object", "properties": {"path": {"type": "string"}}},
                coeffects=["filesystem:write"],
                reversible=False,
            ),
            handler=lambda path: f"wrote:{path}",
        )
    )

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.file_write", args={"path": "x"}, is_irreversible=True)
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, tools=provider, gate=PermissionGuard(mode="read-only"))
    result = loop.run("hi")
    assert result.reply.startswith("已拒绝")


# ---- judgment 三决策点 DI ----


class _FakeRouter:
    def __init__(self) -> None:
        self.calls = 0

    def choose(self, state, options):
        self.calls += 1
        return DecisionResult(
            primitive=DecisionPrimitive.CHOICE,
            answers={"choice": {"choice": options[0]}},
            fallback=False,
        )


class _FakeCompactor:
    def __init__(self) -> None:
        self.calls = 0

    def score(self, state, items, threshold=None):
        self.calls += 1
        return DecisionResult(primitive=DecisionPrimitive.SCORE, answers={}, fallback=False)


class _FakeGuardrail:
    def __init__(self) -> None:
        self.calls = 0

    def check(self, state, action, threshold=None):
        self.calls += 1
        return DecisionResult(
            primitive=DecisionPrimitive.NOUL,
            answers={"noul": {"noul": True}},
            fallback=False,
        )


def test_judgment_choice_injected_into_loop() -> None:
    provider = ToolProvider()
    provider.register(_echo_tool())
    router = _FakeRouter()

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "hi"}, is_irreversible=True)
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, tools=provider, router=router)
    result = loop.run("hi")
    assert result.reply == "done"
    assert router.calls == 1


def test_judgment_score_injected_into_memory() -> None:
    compactor = _FakeCompactor()
    memory = MemoryStore(compactor=compactor)
    memory.compact("query")
    assert compactor.calls == 1


def test_judgment_noul_injected_into_permission() -> None:
    guardrail = _FakeGuardrail()
    guard = PermissionGuard(guardrail=guardrail)
    guard.confirm("tools.file_read", {"path": "x"}, ["filesystem:read"], reversible=False)
    assert guardrail.calls == 1


# ---- entry 贯通 ----


def test_entry_run_wires_runtime(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class _FakeRuntime:
        def __init__(self) -> None:
            self.loop = object()
            self.memory = object()
            self.tools = object()
            self.config = object()
            self.app = SimpleNamespace(llm=SimpleNamespace(api_key_ref="${KEY}"))

    def _fake_build(config):
        calls["config"] = config
        return _FakeRuntime()

    class _FakeAPI:
        def __init__(self, **kwargs) -> None:
            calls["kwargs"] = kwargs

        def create_session(self, mode: str) -> str:
            return "sess-1"

        def set_llm_config(self, cfg) -> None:
            calls["llm_cfg"] = cfg

        async def run_loop(self, session_id: str, user_input: str):
            if False:
                yield None

    monkeypatch.setattr(entry, "build_runtime", _fake_build)
    monkeypatch.setattr(entry, "UIAPILayer", _FakeAPI)

    args = argparse.Namespace(prompt="你好", file=None, session_id=None, config=None)
    assert entry._run(args) == 0
    assert calls["config"] is not None
    assert calls["llm_cfg"].api_key_ref == "${KEY}"
    assert calls["kwargs"]["loop"] is not None
    assert calls["kwargs"]["memory"] is not None
