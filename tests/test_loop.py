"""loop 单元测试（对齐 §14 契约 + M2 验收锚点）。

覆盖：停止条件退出 / 单轮失败回滚 / 中间件被拒短路 / 循环与 token 超限 /
同步异步等价 / 端到端冒烟（loop 驱动 tool-use + memory）。
"""

from __future__ import annotations

import asyncio

from core.loop import Action, DefaultLoop
from core.memory import MemoryStore
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


class _SpyProvider(ToolProvider):
    """记录回滚调用，验证单轮失败触发回滚。"""

    def __init__(self) -> None:
        super().__init__()
        self.rolled_back: list[str | None] = []

    def rollback(self, trace_id: str | None = None):
        self.rolled_back.append(trace_id)
        return super().rollback(trace_id)


# ---- 终端动作 ----


def test_run_terminal_reply() -> None:
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "你好"}))
    result = loop.run("问题")
    assert result.reply == "你好"
    assert result.trace_id


# ---- 中间件短路 ----


def test_middleware_reject_short_circuits() -> None:
    def planner(ctx):
        return Action(tool_id="tools.echo", args={"text": "hi"})

    loop = DefaultLoop(planner=planner, middlewares=[lambda ctx, action: None], max_rounds=3)
    result = loop.run("hi")
    assert result.reply.startswith("已拒绝")


# ---- 循环 / token 超限 ----


def test_max_rounds_limit() -> None:
    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.echo", args={"text": "x"}), max_rounds=2
    )
    result = loop.run("hi")
    assert "LOOP_LIMIT_EXCEEDED" in result.reply


def test_token_budget_limit() -> None:
    loop = DefaultLoop(
        planner=lambda ctx: Action(tool_id="tools.echo", args={"text": "x"}), token_budget=1
    )
    result = loop.run("hi")
    assert "TOKEN_BUDGET_EXCEEDED" in result.reply


# ---- 单轮失败回滚 ----


def test_single_round_failure_rolls_back() -> None:
    provider = _SpyProvider()
    provider.register(
        Tool(
            definition=ToolDef(
                tool_id="tools.fail",
                description="",
                schema={"type": "object"},
                coeffects=["filesystem:write"],  # 未注册 → CoeffectMissing → 本轮失败
                reversible=False,
            ),
            handler=lambda: "x",
        )
    )

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.fail", args={})
        return Action(args={"reply": "done"})

    loop = DefaultLoop(planner=planner, tools=provider, max_rounds=5)
    result = loop.run("hi")
    assert result.reply == "done"
    assert provider.rolled_back  # 单轮失败触发回滚


# ---- 同步 / 异步等价 ----


def test_run_arun_equivalent() -> None:
    loop = DefaultLoop(planner=lambda ctx: Action(args={"reply": "ok"}))
    sync = loop.run("hi")
    async_result = asyncio.run(loop.arun("hi"))
    assert sync.reply == async_result.reply == "ok"
    assert sync.trace_id
    assert async_result.trace_id


# ---- 端到端冒烟：loop 驱动 tool-use + memory ----


def test_e2e_loop_drives_tool_and_memory() -> None:
    provider = ToolProvider()
    provider.register(_echo_tool())
    memory = MemoryStore()

    def planner(ctx):
        if ctx.rounds == 0:
            return Action(tool_id="tools.echo", args={"text": "hi"})
        return Action(args={"reply": f"完成 {ctx.rounds} 步"})

    loop = DefaultLoop(planner=planner, tools=provider, memory=memory)
    result = loop.run("hello")
    assert result.reply == "完成 1 步"
    assert result.trace_id
    # 记忆写入：remember 落 L2 轨迹，按 trace 可审计
    assert memory.audit(result.trace_id) != []
