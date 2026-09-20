"""智能体循环接口协议骨架（L3 Loop）。

把 doc/03-interfaces/loop-interface.md 的接口契约提炼为
typing.Protocol 骨架：只声明方法签名与 docstring，不含实现。

对应规格：doc/openspec/specs/loop/spec.md
模块设计：doc/02-modules/loop.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LoopResult:
    """一轮闭环的最终产物。"""

    reply: str                 # 最终回复
    trace_id: str              # 本轮追溯 ID（贯穿日志/效应/记忆）


@dataclass
class LoopContext:
    """一轮循环中的上下文包（token 有硬上界）。"""

    messages: list[Any]        # 本轮消息流（Message）
    memory: Any                # 检索结果 + L1 索引（MemoryPack，有 token 上界）
    tools: list[Any]           # 可调用工具 schema（ToolSchema）
    trajectory: list[Any]      # 本轮轨迹（Step，供 Remember 写入）
    reply: str = ""

    def done(self) -> bool:
        """推理判定可结束本轮时返回 True。"""
        raise NotImplementedError


@dataclass
class Action:
    """模型决策的下一步动作。"""

    is_irreversible: bool = False   # True → 触发确认门


@dataclass
class ActionResult:
    """动作执行结果。"""

    failed: bool = False            # True → 回滚本轮


class LoopPlugin(Protocol):
    """Loop 插件接口（策略替换点：ReAct / Plan-Execute / 自定义）。

    装配依赖（coeffects）：模型适配器 + 记忆存储 + 工具提供者 + 元规则。
    对应接口文档中的 ``class LoopPlugin(Plugin)``，Plugin 基类待
    plugin-registry 落地后接入。
    """

    plugin_id: str = "loop.default"
    coeffects: list[str] = [
        "model:adapter", "memory:store", "tools:provider", "constitution:v1",
    ]

    def run(self, user_input: str) -> LoopResult:
        """执行一轮完整闭环：感知 → 推理 → 行动 → 记忆。"""
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
