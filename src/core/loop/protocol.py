"""智能体循环接口协议（L3 Loop）。

把 doc/03-interfaces/loop-interface.md 的接口契约提炼为 typing.Protocol：
LoopPlugin 声明同步 run / 异步 arun / 流式 astream 三入口 + 阶段方法
（perceive / reason / act / observe / remember），DefaultLoop 为默认实现。

对应规格：doc/openspec/specs/loop/spec.md
模块设计：doc/02-modules/loop.md
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LoopResult:
    """一轮闭环的最终产物。"""

    reply: str  # 最终回复
    trace_id: str  # 本轮追溯 ID（贯穿日志/效应/记忆）
    failed: bool = False  # 成败信号：目标未达成/异常终止/预算耗尽为 True


@dataclass
class LoopEvent:
    """执行生命周期事件（loop_started/step_completed/reply_delta/loop_finished/loop_failed）。"""

    type: str
    payload: Any = None


@dataclass
class LoopContext:
    """一轮循环中的上下文包（token 有硬上界）。"""

    messages: list[Any] = field(default_factory=list[Any])
    memory: list[Any] = field(default_factory=list[Any])
    tools: list[Any] = field(default_factory=list[Any])
    trajectory: list[Any] = field(default_factory=list[Any])
    reply: str = ""
    rounds: int = 0
    token_used: int = 0
    _done: bool = field(default=False, repr=False)

    def done(self) -> bool:
        """推理判定可结束本轮时返回 True。"""
        return self._done

    def finish(self) -> None:
        """标记本轮可结束（供循环实现写入）。"""
        self._done = True


@dataclass
class Action:
    """模型决策的下一步动作；tool_id 为空串表示本轮结束（终止动作）。"""

    tool_id: str = ""
    args: dict[str, Any] = field(default_factory=dict[str, Any])
    is_irreversible: bool = False

    @property
    def is_terminal(self) -> bool:
        return not self.tool_id


@dataclass
class ActionResult:
    """动作执行结果。"""

    failed: bool = False  # True → 回滚本轮
    data: Any = None
    error: str = ""


class LoopPlugin(Protocol):
    """Loop 插件接口（策略替换点：ReAct / Plan-Execute / 自定义）。

    装配依赖（coeffects）：模型适配器 + 记忆存储 + 工具提供者 + 元规则。
    """

    plugin_id: str = "loop.default"
    coeffects: list[str] = [
        "model:adapter",
        "memory:store",
        "tools:provider",
        "constitution:v1",
    ]

    def run(self, user_input: str) -> LoopResult:
        """同步执行入口：经事件循环桥接 arun（薄壳），调用方零改动。"""
        ...

    async def arun(self, user_input: str) -> LoopResult:
        """异步执行入口：与 run 同构，事件循环内非阻塞。"""
        ...

    async def astream(self, user_input: str) -> AsyncIterator[LoopEvent]:
        """流式执行入口：按生命周期顺序产出 LoopEvent 事件流。"""
        ...

    # ---- 阶段方法（私有，但为策略替换点）----

    def perceive(self, user_input: str) -> LoopContext:
        """收集状态，拼上下文包（token 有硬上界，按优先级裁剪）。"""
        ...

    def reason(self, ctx: LoopContext) -> Action:
        """调用模型决策下一步动作（非法动作回传结构化错误，不中断）。"""
        ...

    def act(self, action: Action, trace_id: str) -> ActionResult:
        """执行动作，经 EffectTracker 记录（可回滚；不可逆操作过确认门）。"""
        ...

    def observe(self, ctx: LoopContext, result: ActionResult) -> LoopContext:
        """把动作结果写回上下文，推进循环。"""
        ...

    def remember(self, trace_id: str, trajectory: list[Any]) -> None:
        """写本轮轨迹/教训入 L2/L3（每轮必做，无行动不记忆）。"""
        ...
