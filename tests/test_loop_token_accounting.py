"""loop token 记账口径（change 0152 / 账本 E96）。

覆盖两条接缝：

- ``DefaultLoop`` 记账覆盖**全量装配**（回灌历史 + 本轮消息），并以 planner 探针
  ``last_prompt_tokens()`` 报出的观测为**下界** ⇒ 系统提示与工具 schema 计入，
  预算闸门不再偏晚（真实风险是撞厂商 `context_length_exceeded` 400）；
- ``LLMPlanner.last_prompt_tokens()``：装配全量估算（全部消息 + 工具 schema）持为候选，
  provider 实报 ``usage.prompt_tokens`` 抬升下界；探针缺失 / 异常 ⇒ 退化为纯估算（零回归）。

对应规格：doc/openspec/specs/loop/spec.md「错误与预算控制」记账口径条款
（Scenario: 记账计入系统提示与工具 schema / provider 实报为记账下界）。
"""

from __future__ import annotations

import asyncio

from core.llm_provider import LLMRequest, LLMResponse, TokenUsage
from core.loop import Action, DefaultLoop, LLMPlanner, LoopContext
from core.tools import Tool, ToolDef, ToolProvider

# ---- 替身 ----

_REPORTED_TOKENS = 999  # provider 实报的提示 token 数（哨兵值）


class _ProbePlanner:
    """duck-typed planner：终端回复 + 暴露 ``last_prompt_tokens()`` 探针。"""

    def __init__(self, reported: int) -> None:
        self._reported = reported

    async def __call__(self, ctx: LoopContext) -> Action:
        return Action(args={"reply": "ok"})

    def last_prompt_tokens(self) -> int:
        return self._reported


class _NoProbePlanner:
    """既有形态替身：无探针 ⇒ 记账户退化为估算。"""

    async def __call__(self, ctx: LoopContext) -> Action:
        return Action(args={"reply": "ok"})


class _BrokenProbePlanner:
    """探针抛错 ⇒ 降级为「无观测」，不阻断本轮。"""

    async def __call__(self, ctx: LoopContext) -> Action:
        return Action(args={"reply": "ok"})

    def last_prompt_tokens(self) -> int:
        raise RuntimeError("probe boom")  # noqa: TRY003 — 测试用哨兵异常


class _StubLLM:
    """duck-typed LLM：仅 ``acompletion`` ⇒ planner 走非流式 ``_complete`` 路径。"""

    def __init__(self, response: LLMResponse) -> None:
        self._response = response

    async def acompletion(self, request: LLMRequest) -> LLMResponse:
        return self._response


def _response(prompt_tokens: int) -> LLMResponse:
    """固定响应：``prompt_tokens`` = 0 模拟「provider 未报用量」（如流式响应）。"""
    return LLMResponse(
        content="ok",
        usage=TokenUsage(prompt_tokens=prompt_tokens, completion_tokens=1),
        finish_reason="stop",
        provider="stub",
        model="stub-model",
    )


def _echo_provider() -> ToolProvider:
    provider = ToolProvider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.echo",
                description="把输入原样回显，用于观测工具 schema 是否计入装配估算。",
                schema={"type": "object", "properties": {"text": {"type": "string"}}},
                coeffects=[],
                reversible=True,
            ),
            handler=lambda text: f"echo:{text}",
        )
    )
    return provider


# ---- DefaultLoop：记账口径 ----


def test_gate_uses_planner_reported_prompt_tokens() -> None:
    """planner 探针报出的提示 token 被计入 ⇒ 本轮消息极短也能触发预算终止。

    「本轮 user 只有 2 字符」时旧口径记 0 token ⇒ 闸门看不见真实提示词大小；
    探针报出 10000 ⇒ 超出预算 100，必须终止。
    """
    loop = DefaultLoop(planner=_ProbePlanner(10_000), token_budget=100)
    result = loop.run("hi")

    assert "TOKEN_BUDGET_EXCEEDED" in result.reply
    assert result.failed


def test_no_probe_degrades_to_estimate() -> None:
    """无探针 planner（既有替身形态）⇒ 退化为估算，本轮照常完成（零回归）。"""
    loop = DefaultLoop(planner=_NoProbePlanner(), token_budget=100)
    result = loop.run("hi")

    assert result.reply == "ok"
    assert not result.failed


def test_broken_probe_degrades_without_raising() -> None:
    """探针抛错 ⇒ 当作「无观测」降级，本轮照常完成、不抛裸异常。"""
    loop = DefaultLoop(planner=_BrokenProbePlanner(), token_budget=100)
    result = loop.run("hi")

    assert result.reply == "ok"
    assert not result.failed


# ---- LLMPlanner：探针 ----


def test_planner_probe_estimates_full_assembly_without_usage() -> None:
    """无 usage（未报 / 0）⇒ 按装配全量估算：系统提示前缀**计入**（> 0）。"""
    planner = LLMPlanner(_StubLLM(_response(0)))  # type: ignore[arg-type]
    bare = LoopContext(messages=[{"role": "user", "content": "hi"}])
    pinned = LoopContext(
        messages=[{"role": "user", "content": "hi"}],
        pinned_notes="任务级硬约束：不得删除用户数据。" * 200,
    )

    asyncio.run(planner(pinned))
    with_prefix = planner.last_prompt_tokens()
    asyncio.run(planner(bare))
    without_prefix = planner.last_prompt_tokens()

    assert without_prefix > 0
    assert with_prefix > without_prefix


def test_planner_probe_takes_reported_usage_as_lower_bound() -> None:
    """provider 实报为**下界**：记账值不低于实报值，亦不低于纯估算。"""
    ctx = LoopContext(messages=[{"role": "user", "content": "hi"}])
    plain = LLMPlanner(_StubLLM(_response(0)))  # type: ignore[arg-type]
    asyncio.run(plain(ctx))
    estimate = plain.last_prompt_tokens()

    reporting = LLMPlanner(_StubLLM(_response(_REPORTED_TOKENS)))  # type: ignore[arg-type]
    asyncio.run(reporting(ctx))

    assert reporting.last_prompt_tokens() >= _REPORTED_TOKENS
    assert reporting.last_prompt_tokens() >= estimate


def test_planner_probe_counts_tool_schemas() -> None:
    """工具 schema（及工具清单块）计入装配估算：有工具 > 无工具。"""
    llm = _StubLLM(_response(0))
    ctx = LoopContext(messages=[{"role": "user", "content": "hi"}])
    bare = LLMPlanner(llm)  # type: ignore[arg-type]
    with_tools = LLMPlanner(llm, tools=_echo_provider())  # type: ignore[arg-type]

    asyncio.run(bare(ctx))
    bare_tokens = bare.last_prompt_tokens()
    asyncio.run(with_tools(ctx))
    tools_tokens = with_tools.last_prompt_tokens()

    assert tools_tokens > bare_tokens
