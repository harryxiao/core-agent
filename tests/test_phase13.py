"""Phase 13 系统级接线测试（M9 单 Agent 真闭环）。

覆盖：runtime 组合根装配 + coeffect 缺失拒绝启动；LLMPlanner 接 LLM（含解析失败
错误码）；热路径 TraceEvent 落点；PermissionGuard 不可逆审批 / 拒绝短路；
judgment 三决策点（loop choice / memory score / permission noul）注入断言；
entry 贯通装配。
"""

from __future__ import annotations

import argparse
import asyncio
from types import SimpleNamespace

import pytest

from core import entry
from core.configuration import ConfigManager, ConfigurationError
from core.context import DynamicAssembler
from core.judgment import DecisionPrimitive, DecisionResult, SkillMatcher
from core.llm_provider import Embedding, LLMChunk, LLMError, LLMResponse, TokenUsage, ToolCall
from core.loop import (
    Action,
    DefaultLoop,
    LLMPlanner,
    LoopContext,
    LoopResult,
    Thinking,
    current_session_id,
)
from core.memory import MemoryEntry, MemoryStore
from core.observability import TraceEvent, Tracer
from core.permission import PermissionGuard
from core.runtime import build_runtime
from core.skills import Skill, SopExtractor
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


class _CapturingExporter:
    """收集封口交付的事件（落盘真路径的桩，change 0103）。"""

    def __init__(self) -> None:
        self.batches: list[list[TraceEvent]] = []

    def emit(self, events: list[TraceEvent]) -> None:
        self.batches.append(list(events))

    @property
    def events(self) -> list[TraceEvent]:
        return [event for batch in self.batches for event in batch]


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

    async def acompletion(self, request: object) -> LLMResponse:
        return self.completion(request)


def _write_config(tmp_path, *, embedding_model: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    embed_line = f"  embedding_model: {embedding_model}\n" if embedding_model else ""
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n"
        "  reasoning_effort: low\n" + embed_line,
        encoding="utf-8",
    )
    return str(cfg)


# ---- runtime 组合根 ----


def test_build_runtime_assembles_all_deps(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert runtime.app.llm.model == "test-model"
    assert runtime.app.llm.reasoning_effort == "low"
    assert runtime.llm is not None
    assert runtime.memory is not None
    assert runtime.tools is not None
    assert runtime.tracer is not None
    assert runtime.router is not None
    assert runtime.loop is not None
    ids = {t.tool_id for t in runtime.tools.active_tools()}
    assert ids == {
        "tools.file_read",
        "tools.file_write",
        "tools.file_patch",
        "tools.code_run",
        "tools.web_fetch",
        "tools.delegate",
        # 插件安装工具（change 0108 / 账本 E33）：生产工具面可达
        "tools.install",
        "tools.uninstall",
        "tools.list",
        # 质量门禁工具（change 0111 / phase-27 切片 S1）：生产工具面可达
        "tools.gate_run",
        # 信息地图取详情工具（change 0140 / 账本 E77）：生产工具面可达
        "tools.context_read",
        # 后台任务巡检 / 终止（change 0259 / ADR-0249）：生产工具面可达
        "tools.process",
        "tools.process_kill",
        # 后台子 Agent 任务清单（change 0270 / ADR-0260）：生产工具面可达
        "tools.tasks",
        # 后台任务重入队（change 0279 / ADR-0269）：生产工具面可达
        "tools.task_retry",
        # 工具参数按需查询（change 0272 / ADR-0262）：生产工具面可达
        "tools.schema_read",
    }
    delegate = next(t for t in runtime.tools.active_tools() if t.tool_id == "tools.delegate")
    min_delegate_timeout = 120.0  # 委托跑完整子循环，远超 ToolDef 默认 30s
    assert delegate.timeout_s >= min_delegate_timeout
    # 委托驱动子 loop 属跨边界能力，须显式声明 coeffect（否则 MCP 默认暴露面看不见它，账本 B7）
    assert delegate.coeffects == ["agent:delegate"]

    # MCP 默认暴露面（未配置白名单）不得含 delegate / web_fetch（账本 B7 收窄）
    from core.mcp import MCPServer, ServerConnection  # noqa: PLC0415 — 就地验证默认面

    server = MCPServer(tool_provider=runtime.tools)
    conn = ServerConnection(connection_id="c1", session_id="s1", client_id="ext")
    exposed = {t.name for t in server.list_tools(conn)}
    assert "core.tools.delegate" not in exposed
    assert "core.tools.web_fetch" not in exposed
    assert "core.tools.file_read" in exposed


# ---- constraints 中间件链注入（change 0052 / E1）----


def test_build_runtime_injects_shared_constraints_chain(monkeypatch, tmp_path) -> None:
    """组合根把同一 constraints 链注入主 loop 与所有子 agent loop（熔断态 per-runtime）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert runtime.loop._middlewares, "主 loop 必须注入 constraints 中间件链"
    assert runtime.loop._action_observers, "主 loop 必须注入结果侧观察者"
    main_chain = runtime.loop._middlewares[0].__self__

    router = runtime.orchestrator._router
    profiles = list(router._agents.values())
    if router._fallback is not None:
        profiles.append(router._fallback)
    assert profiles, "应有子 agent 画像"
    for profile in profiles:
        sub = profile.loop
        assert sub._middlewares[0].__self__ is main_chain, "子 loop 必须共享同一熔断链"
        assert sub._action_observers[0].__self__ is main_chain


def test_build_runtime_wires_core_profile_into_assembler(monkeypatch, tmp_path) -> None:
    """P0：两级 Core.md 的宪法/项目信息经 build_runtime 接进装配器。

    此前 build_runtime 从不传 assembler= → planner._assembler is None → 事实注入从未发生。
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME", str(tmp_path))  # 隔离全局级，避免读到真实 ~/.core/Core.md
    core_dir = tmp_path / ".core"
    core_dir.mkdir()
    (core_dir / "Core.md").write_text("## 宪法与全局规则\n- 必须保持简洁\n", encoding="utf-8")
    project = tmp_path / "proj"
    project.mkdir()
    (project / "Core.md").write_text("## 项目信息\n- 本项目用 uv 管理\n", encoding="utf-8")
    monkeypatch.chdir(project)  # 项目级按 cwd 向上查找命中

    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    planner = runtime.loop._planner
    assert planner._assembler is not None, "build_runtime 必须把装配器接进 planner（P0）"
    pack = planner._assembler.build("任务", "reason", budget=2048)
    assert any("必须保持简洁" in line for line in pack.constitution)
    assert any("本项目用 uv 管理" in f["content"] for f in pack.facts)


def test_build_runtime_writes_personality_to_l0_memory(monkeypatch, tmp_path) -> None:
    """core-profile spec「双语义分区」：人格分区落 L0 记忆层（P0b），稳定 id 幂等写入。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME", str(tmp_path))
    core_dir = tmp_path / ".core"
    core_dir.mkdir()
    (core_dir / "Core.md").write_text(
        "## 人格\n- 身份：严谨的工程助手\n- 沟通风格：简洁直接\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)  # 无项目级 Core.md

    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    l0 = [e for e in runtime.memory.read("人格", budget=2048) if e.layer == "L0"]
    assert any("严谨的工程助手" in e.content for e in l0), "人格应落入 L0 记忆层"

    # 幂等：再次装配（同 HOME/state）不新增条目——稳定 id 覆盖
    runtime2 = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    l0_ids = [e.id for e in runtime2.memory.read("人格", budget=2048) if e.layer == "L0"]
    assert l0_ids == ["core-profile:personality"]


def test_build_runtime_memory_persists_to_state_dir(monkeypatch, tmp_path) -> None:
    """默认装配的记忆后端落盘到 $CORE_STATE_DIR（新后端可重载检索，不因进程退出丢失）。"""
    import os  # noqa: PLC0415 — 断言用环境变量
    from pathlib import Path  # noqa: PLC0415 — 断言用落盘路径

    from core.memory import FileBackend, MemoryEntry  # noqa: PLC0415 — 重载后端

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    runtime.memory.write(
        "L2",
        MemoryEntry(
            id="m1",
            layer="L2",
            content="持久化验证内容",
            tags=["t"],
            source="loop",
            trace_id="tr1",
        ),
    )
    path = Path(os.environ["CORE_STATE_DIR"]) / "memory.jsonl"
    assert path.exists()  # 默认后端已落盘（而非纯内存）
    reloaded = MemoryStore(backend=FileBackend(path))
    assert [e.id for e in reloaded.read("持久化验证内容")] == ["m1"]


def test_subagents_isolated_loops_without_delegate(monkeypatch, tmp_path) -> None:
    """子 Agent 独立 loop（非主 loop）且工具面不含 delegate（结构上杜绝再委托）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    router = runtime.orchestrator._router  # noqa: SLF001 — 校验装配产物
    profiles = list(router._agents.values())  # noqa: SLF001
    assert {p.agent_id for p in profiles} == {"coding", "research"}
    for profile in profiles:
        assert profile.loop is not runtime.loop  # 独立 loop 实例（非主 loop）
        sub_tools = {t.tool_id for t in profile.loop._tools.active_tools()}  # noqa: SLF001
        assert "tools.delegate" not in sub_tools


def test_delegate_depth_guard_blocks_nested(monkeypatch, tmp_path) -> None:
    """委托深度护栏：已在委托中（depth>=1）再委托被拒，防无限递归。"""
    from core import runtime as runtime_module  # noqa: PLC0415 — 访问模块级护栏

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    token = runtime_module._DELEGATE_DEPTH.set(1)  # noqa: SLF001 — 模拟身处子委托
    try:
        result = asyncio.run(
            runtime.tools.ainvoke("tools.delegate", {"task": "写代码"}, trace_id="t1")
        )
    finally:
        runtime_module._DELEGATE_DEPTH.reset(token)
    assert result.ok is True  # 工具正常返回
    assert result.data["ok"] is False  # 但委托被护栏拒绝
    assert "深度上限" in result.data["error"]


def test_delegate_forwards_current_session_to_subagent(monkeypatch, tmp_path) -> None:
    """委托把发起会话转交子 Agent（change 0247）：子 loop 收到同一 session_id。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    router = runtime.orchestrator._router  # noqa: SLF001 — 校验装配产物
    coding = router._agents["coding"].loop  # noqa: SLF001
    seen: list[str] = []

    async def _fake_arun(task: str, *, session_id: str = "") -> LoopResult:
        seen.append(session_id)
        return LoopResult(reply="ok", trace_id="t1")

    monkeypatch.setattr(coding, "arun", _fake_arun)
    token = current_session_id.set("sess-7")
    try:
        result = asyncio.run(
            runtime.tools.ainvoke("tools.delegate", {"task": "写代码"}, trace_id="t1")
        )
    finally:
        current_session_id.reset(token)
    assert result.ok is True
    assert result.data["ok"] is True
    assert seen == ["sess-7"]


def test_general_fallback_handles_unmatched_subtask(monkeypatch, tmp_path) -> None:
    """无 capability 命中的子任务回落 general 画像（不再 NO_AGENT_MATCH 整条失败）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    router = runtime.orchestrator._router  # noqa: SLF001 — 校验装配产物
    for goal in ("整理一份季度总结", "写一篇散文"):
        assert router.match(goal).agent_id == "general"


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
        fake,
        reasoning_effort="low",
        assembler=assembler,
        skill_router=lambda task: [
            {"skill_id": "skills.x.y", "version": "v2", "instructions": "1. 读输入"}
        ],
        tools=provider,
    )

    action = asyncio.run(planner(LoopContext(messages=[{"role": "user", "content": "hi"}])))

    assert action.tool_id == "tools.echo"
    assert action.args == {"text": "hi"}
    request = fake.requests[0]
    assert request.reasoning_effort == "low"
    # 工具以 OpenAI function 信封进 LLMRequest.tools；宪法/技能进 system prompt
    tools = request.tools or []
    assert tools and tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "tools.echo"
    system = request.messages[0].content
    assert "skills.x.y（v2）" in system, "技能块含 id 与版本"
    assert "1. 读输入" in system, "命中注入 instructions（0045）"
    assert tools[0]["function"]["parameters"] == provider.active_tools()[0].schema
    system = request.messages[0].content
    assert "规则A" in system
    assert "skills.x.y" in system


def test_llm_planner_parse_failure_error_code() -> None:
    planner = LLMPlanner(_FakeLLM('{"tool_id": "tools.echo",'))
    action = asyncio.run(planner(LoopContext(messages=[{"role": "user", "content": "hi"}])))
    assert "LLM_PLAN_PARSE_FAILED" in action.args["reply"]


def test_llm_planner_plain_text_reply() -> None:
    planner = LLMPlanner(_FakeLLM("直接回复文本"))
    action = asyncio.run(planner(LoopContext(messages=[{"role": "user", "content": "hi"}])))
    assert action.args == {"reply": "直接回复文本"}
    assert action.is_terminal


def test_loop_uses_async_llm_without_nested_loop() -> None:
    """真 LLM 同步薄壳经 asyncio.run 桥接：loop 应走异步 acompletion，不触发嵌套事件循环。"""

    class _ThinShellLLM:
        def __init__(self, content: str) -> None:
            self._content = content

        async def acompletion(self, request: object) -> LLMResponse:
            return LLMResponse(
                content=self._content,
                usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
                finish_reason="stop",
                provider="fake",
                model="test-model",
            )

        def completion(self, request: object) -> LLMResponse:
            return asyncio.run(self.acompletion(request))

    loop = DefaultLoop(planner=LLMPlanner(_ThinShellLLM("直接回复文本")))
    result = loop.run("问题")
    assert result.reply == "直接回复文本"


# ---- LLMPlanner 流式推理 ----


class _StreamingFakeLLM:
    """记录 LLMRequest、按固定分片流式产出的假 LLM（str 分片或整 LLMChunk）。"""

    def __init__(self, chunks: list[str | LLMChunk]) -> None:
        self._chunks = chunks
        self.requests: list[object] = []

    async def astream(self, request: object):
        self.requests.append(request)
        for item in self._chunks:
            yield item if isinstance(item, LLMChunk) else LLMChunk(content=str(item))


def _collect_planner_stream(planner: LLMPlanner) -> list[str | Action | Thinking]:
    async def _run() -> list[str | Action | Thinking]:
        return [item async for item in planner.astream(LoopContext(messages=["hi"]))]

    return asyncio.run(_run())


def test_planner_astream_yields_reply_deltas() -> None:
    """自然语言回复：逐 delta 外发，末态 Action 携带全文。"""
    planner = LLMPlanner(_StreamingFakeLLM(["你", "好", "，", "世界"]))
    items = _collect_planner_stream(planner)
    assert items == ["你", "好", "，", "世界", Action(args={"reply": "你好，世界"})]


def test_planner_astream_buffers_tool_call_json() -> None:
    """工具调用 JSON：分片缓冲不外泄半截 JSON，末态解析为工具 Action。"""
    planner = LLMPlanner(
        _StreamingFakeLLM(['{"tool_id": "tools.', 'echo", "args": {"text": "hi"}}'])
    )
    items = _collect_planner_stream(planner)
    assert items == [Action(tool_id="tools.echo", args={"text": "hi"})]


def test_planner_astream_llm_error_returns_action() -> None:
    """流式失败与 __call__ 同语义：终端回复错误信息，不抛裸异常。"""

    class _BrokenLLM:
        async def astream(self, request: object):
            raise LLMError("boom")
            yield  # pragma: no cover — 使其为异步生成器

    planner = LLMPlanner(_BrokenLLM())
    items = _collect_planner_stream(planner)
    assert len(items) == 1 and "LLM 调用失败" in items[0].args["reply"]


# ---- 原生 tool_calls 协议 ----


class _NativeToolLLM:
    """非流式返回原生 tool_calls 的假 LLM。"""

    def __init__(self, tool_calls: list[ToolCall]) -> None:
        self._tool_calls = tool_calls

    async def acompletion(self, request: object) -> LLMResponse:
        return LLMResponse(
            content="",
            usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
            finish_reason="tool_calls",
            provider="fake",
            model="test-model",
            tool_calls=self._tool_calls,
        )


def test_planner_parses_native_tool_calls() -> None:
    """原生 tool_calls → 工具 Action（优先于 content 协议）。"""
    planner = LLMPlanner(
        _NativeToolLLM([ToolCall(tool_id="tools.echo", arguments='{"text": "hi"}')])
    )
    action = asyncio.run(planner(LoopContext(messages=["hi"])))
    assert action.tool_id == "tools.echo"
    assert action.args == {"text": "hi"}
    assert not action.is_irreversible


def test_planner_native_tool_call_bad_arguments() -> None:
    """参数 JSON 非法 → 结构化解析错误码（不抛裸异常）。"""
    planner = LLMPlanner(_NativeToolLLM([ToolCall(tool_id="tools.echo", arguments="{oops")]))
    action = asyncio.run(planner(LoopContext(messages=["hi"])))
    assert "LLM_PLAN_PARSE_FAILED" in action.args["reply"]


def test_planner_astream_accumulates_native_tool_fragments() -> None:
    """流式原生片段按 index 累积 name/arguments，不外泄半截，末态工具 Action。"""
    fake = _StreamingFakeLLM(
        [
            LLMChunk(
                content="",
                tool_calls=[ToolCall(tool_id="tools.echo", arguments="", call_id="c1")],
            ),
            LLMChunk(content="", tool_calls=[ToolCall(tool_id="", arguments='{"text"')]),
            LLMChunk(content="", tool_calls=[ToolCall(tool_id="", arguments=': "hi"}')]),
        ]
    )
    items = _collect_planner_stream(LLMPlanner(fake))
    assert items == [Action(tool_id="tools.echo", args={"text": "hi"})]


# ---- 思考回显通道（change 0145 / 账本 E57）----


class _CompletionOnlyLLM:
    """仅支持非流式 ``acompletion`` 的假 LLM（携推理原文）。"""

    def __init__(self, content: str, thinking: str = "") -> None:
        self._content = content
        self._thinking = thinking

    async def acompletion(self, request: object) -> LLMResponse:
        return LLMResponse(
            content=self._content,
            usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
            finish_reason="stop",
            provider="fake",
            model="test-model",
            thinking=self._thinking,
        )


def test_planner_astream_emits_thinking_when_enabled() -> None:
    """开启思考回显：推理原文增量以 `Thinking` item 外发，与回复增量并存互不干扰。"""
    planner = LLMPlanner(
        _StreamingFakeLLM(
            [
                LLMChunk(content="", thinking="想"),
                LLMChunk(content="", thinking="一下"),
                LLMChunk(content="好"),
            ]
        ),
        show_thinking=True,
    )
    assert _collect_planner_stream(planner) == [
        Thinking("想"),
        Thinking("一下"),
        "好",
        Action(args={"reply": "好"}),
    ]


def test_planner_astream_no_thinking_when_disabled() -> None:
    """关闭（缺省）：事件面**零新增**，既有流式语义逐字一致。"""
    planner = LLMPlanner(
        _StreamingFakeLLM([LLMChunk(content="", thinking="想"), LLMChunk(content="好")])
    )
    assert _collect_planner_stream(planner) == ["好", Action(args={"reply": "好"})]


def test_planner_degraded_stream_emits_terminal_thinking() -> None:
    """provider 无 `astream` ⇒ 降级分支以一次性全文外发终态思考（先于终态动作）。"""
    planner = LLMPlanner(_CompletionOnlyLLM("好", "思考全文"), show_thinking=True)
    assert _collect_planner_stream(planner) == [
        Thinking("思考全文"),
        Action(args={"reply": "好"}),
    ]


def test_planner_degraded_stream_no_thinking_when_disabled() -> None:
    """降级分支同样守开关：关闭时零新增，与非流式既有语义一致。"""
    planner = LLMPlanner(_CompletionOnlyLLM("好", "思考全文"))
    assert _collect_planner_stream(planner) == [Action(args={"reply": "好"})]


# ---- 热路径 TraceEvent ----


def test_loop_emits_trace_events() -> None:
    exporter = _CapturingExporter()
    loop = DefaultLoop(
        planner=lambda ctx: Action(args={"reply": "ok"}), tracer=Tracer(exporter=exporter)
    )
    loop.run("hi")
    kinds = {e.kind for e in exporter.events}
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
            self.orchestrator = object()
            self.pet_activator = object()
            self.pet_manager = None  # _build_ui 若接了则构造控制门面（此处不接）
            self.beast_activator = None  # change 0137：`_build_ui` 读该字段（此处不接）
            self.transcript = None  # change 0115：_build_ui 读该字段（此处不接转录）
            self.env_snapshot = None  # change 0240：_build_ui 读该字段（标题用中性 Shell）
            self.app = SimpleNamespace(llm=SimpleNamespace(api_key_ref="${KEY}"))

        def recover(self):  # change 0207：`run` 入口启动扫描调 `runtime.recover()`
            return []

        def recover_turns(self):  # change 0214：轮面独立呈现面（此处无中止轮）
            return []

    def _fake_build(config, **kwargs):
        calls["config"] = config
        calls["build_kwargs"] = kwargs
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
    assert calls["kwargs"]["approval"] is None  # 非交互入口无审批通道（fail-closed）
    assert calls["build_kwargs"]["approver"] is None


def test_build_runtime_embedder_di_passthrough(monkeypatch, tmp_path) -> None:
    """build_runtime 透传 embedder DI 参数；默认 None（词法路径不变）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)

    def fake_embedder(texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    assert runtime.memory._embedder is None

    runtime2 = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path)), embedder=fake_embedder
    )
    assert runtime2.memory._embedder is fake_embedder


def _fake_provider_cls(
    constructed: list[tuple[str, str | None]],
    *,
    fail: bool = False,
    calls: list[list[str]] | None = None,
):
    """假 provider 类：记录 (model, base_url)，embedding 返回定长向量或抛错（不触网）。"""

    class _FakeProvider:
        def __init__(  # noqa: PLR0913 — 桩镜像 provider 构造签名
            self,
            *,
            api_key: str,
            base_url: str | None,
            model: str,
            provider: str = "",
            timeout: float = 60.0,
            max_retries: int = 3,
        ) -> None:
            constructed.append((model, base_url))

        def embedding(self, texts: list[str]) -> list[Embedding]:
            if calls is not None:
                calls.append(list(texts))
            if fail:
                raise LLMError("embedding unreachable")  # noqa: TRY003 — 模拟端点不可达
            return [Embedding(vector=[float(len(t))]) for t in texts]

    return _FakeProvider


def test_build_runtime_embedding_model_wires_batched_embedder(monkeypatch, tmp_path) -> None:
    """llm.embedding_model 非空 → 该模型另构造 provider → 批量 embedder 注入 memory。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    constructed: list[tuple[str, str | None]] = []
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "core.runtime.StdlibLLMProvider", _fake_provider_cls(constructed, calls=calls)
    )

    rt = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, embedding_model="text-embed-3"))
    )

    # 独立 provider：embedding 用自己的模型名，复用 endpoint
    assert ("text-embed-3", "https://example.com/v1") in constructed
    assert ("test-model", "https://example.com/v1") in constructed
    embedder = rt.memory._embedder
    assert embedder is not None
    assert embedder(["ab", "cde"]) == [[2.0], [3.0]]
    assert calls == [["ab", "cde"]], "批量契约：一次 provider 调用收齐，而不是逐条"


def test_build_runtime_embedding_unreachable_degrades_to_lexical(monkeypatch, tmp_path) -> None:
    """embedding 不可达：启动不阻断，记忆检索降级词法仍可用。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    constructed: list[tuple[str, str | None]] = []
    fake_cls = _fake_provider_cls(constructed, fail=True)
    monkeypatch.setattr("core.runtime.StdlibLLMProvider", fake_cls)

    rt = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, embedding_model="text-embed-3"))
    )

    assert rt.memory._embedder is not None
    rt.memory.write(
        "L2",
        MemoryEntry(id="m1", layer="L2", content="部署流程", tags=[], source="loop", trace_id="t1"),
    )
    assert [h.id for h in rt.memory.read("部署")] == ["m1"]


def test_build_runtime_wires_summarizer_and_context_compactor(monkeypatch, tmp_path) -> None:
    """0041：runtime 注入 LLM 摘要适配器（memory）与上下文压实器（loop 触发点）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert runtime.memory._summarizer is not None, "memory 注入摘要接缝（LLM 提炼）"
    compactor = runtime.loop._compactor
    assert compactor is not None, "loop 注入压实器（预算/轮数触发）"
    assert compactor._memory is runtime.memory, "压实器回写同一记忆存储"


def test_build_runtime_wires_sop_extractor(monkeypatch, tmp_path) -> None:
    """0043/0045：build_runtime 把 SOP 提炼器接进 loop 收尾钩子（产物进 planner 同一技能库）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    observer = runtime.loop._turn_observer
    assert observer is not None, "loop 注入收尾钩子"
    extractor = runtime.skill_extractor
    assert isinstance(extractor, SopExtractor)
    assert extractor._writer is not None, "已配置模型 → 注入提炼接缝"
    assert extractor._tracker is not None, "入库可逆（效应追踪已接）"

    planner = runtime.loop._planner
    assert planner._skill_router("summarize the report") == [], "提炼前技能库为空"

    extractor._writer = lambda prompt: "1. 读输入\n2. 输出摘要"
    for _ in range(3):
        observer("summarize the report", ["assistant: tools.echo", "tool: ok"], True)

    assert planner._skill_router("please summarize the report"), "提炼产物进同一技能库 → 路由命中"


# ---- 0044 语义路由接线 ----


def _write_jev_config(tmp_path) -> str:
    """LLM + JEV 两段配置（judgment 打分能力开启）。"""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n"
        "  reasoning_effort: low\n"
        "judgment:\n"
        "  provider: jev\n"
        "  model: systemone\n"
        "  base_url: http://jev.local\n"
        "  api_key: ${JEV_API_KEY}\n",
        encoding="utf-8",
    )
    return str(cfg)


def test_build_runtime_wires_skill_scorer_with_jev(monkeypatch, tmp_path) -> None:
    """0044：配置 JEV → 语义打分器接进 SkillRouter（词法 miss 时兜底取用技能）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("JEV_API_KEY", "jev-sk")
    runtime = build_runtime(ConfigManager(yaml_path=_write_jev_config(tmp_path)))

    scorer = runtime.skill_router._scorer
    assert scorer is not None, "JEV 配置 → 注入语义打分器"
    assert isinstance(scorer.__self__, SkillMatcher), "注入 SkillMatcher.score 绑定方法"
    assert scorer.__self__._router is runtime.router, "打分走同一 DecisionRouter"

    runtime.skill_router._library.register(
        Skill(
            skill_id="skills.data.summarize",
            description="SOP：summarize report",
            task_types=["summarize report"],
            instructions="1. 读输入\n2. 输出摘要",
            status="active",
        )
    )
    planner_router = runtime.loop._planner._skill_router
    assert planner_router("整理会议纪要") == [], "词法不相交 → 无命中"

    # 桩打分器按 skill_id 点名（不依赖候选次序；库中已有其它常驻技能，change 0106）
    runtime.skill_router._scorer = lambda task, skills: {
        s["skill_id"]: 0.9 for s in skills if s["skill_id"] == "skills.data.summarize"
    }
    hints = planner_router("整理会议纪要")
    assert [h["skill_id"] for h in hints] == ["skills.data.summarize"], "语义兜底 → 技能进 prompt"


def test_build_runtime_without_jev_keeps_lexical_routing(monkeypatch, tmp_path) -> None:
    """0044：未配置 JEV → 不注入打分器，路由零行为变化（纯词法）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    assert runtime.skill_router._scorer is None


# ---- 0045 技能迭代接线 ----


def test_build_runtime_wires_skill_iteration(monkeypatch, tmp_path) -> None:
    """0045：命中注入 instructions → 收尾反馈累计 → 失败率不达标自动迭代（复用 VersionManager）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    library = runtime.skill_router._library
    library.register(
        Skill(
            skill_id="skills.sop.x",
            description="SOP：summarize report",
            task_types=["summarize report"],
            instructions="1. 读输入",
            status="active",
        )
    )
    planner_router = runtime.loop._planner._skill_router
    runtime.skill_iterator._writer = lambda prompt: "1. 改进步骤"
    rounds: list[list[dict[str, str]]] = []
    for _ in range(3):
        rounds.append(planner_router("summarize report"))  # 每轮推理前路由命中（loop 真实节奏）
        runtime.loop._turn_observer("summarize report", ["assistant: x"], False)

    assert [h["instructions"] for h in rounds[0]] == ["1. 读输入"], "命中注入 instructions"
    assert rounds[0][0]["version"] == "v1"

    stats = runtime.skill_feedback.stats("skills.sop.x")
    assert (stats.hits, stats.fail) == (3, 3), "命中与失败累计（钩子带来 ok=False）"
    iterator = runtime.skill_iterator
    assert iterator._drafts["skills.sop.x"]["v2"] == "1. 改进步骤", "自动迭代出草稿"
    assert iterator._versions._gray["skills.sop.x"][0] == "v2", "草稿进入灰度"

    # 灰度是概率分流（样本归属不确定）→ 显式补足两版本样本后再定夺
    samples = runtime.skill_iterator._min_samples
    for _ in range(samples):
        runtime.skill_feedback.record_outcome("skills.sop.x", version="v1", ok=False)
    for _ in range(samples):
        runtime.skill_feedback.record_outcome("skills.sop.x", version="v2", ok=True)
    result = runtime.skill_iterator.decide(library.lookup("skills.sop.x"))

    assert result is not None and result.decision == "promote", "A/B 指标接的是反馈成功率"
    assert library.lookup("skills.sop.x").version == "v2"
    assert library.lookup("skills.sop.x").instructions == "1. 改进步骤"


def test_build_runtime_forwards_failure_steps_to_iterator(monkeypatch, tmp_path) -> None:
    """0223：失败轮把**本轮实际步骤**交给迭代器改写器（凭材料而非仅计数）。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))

    library = runtime.skill_router._library
    library.register(
        Skill(
            skill_id="skills.sop.x",
            description="SOP：summarize report",
            task_types=["summarize report"],
            instructions="1. 读输入",
            status="active",
        )
    )
    planner_router = runtime.loop._planner._skill_router
    seen: list[str] = []
    runtime.skill_iterator._writer = lambda prompt: seen.append(prompt) or "1. 改进步骤"
    for _ in range(3):
        planner_router("summarize report")
        runtime.loop._turn_observer("summarize report", ["code_run（pytest -q）→ 3 failed"], False)

    assert seen, "失败率达阈值 → 已触发改写"
    assert "最近一次失败的实际执行步骤：" in seen[0]
    assert "- code_run（pytest -q）→ 3 failed" in seen[0], "失败现场逐条注入"
