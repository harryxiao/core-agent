"""智能体循环（L3 Loop）。

「观察→推理→行动→记忆」单轮闭环：LoopPlugin 协议声明三入口（run/arun/
astream）+ 五阶段方法，DefaultLoop 为默认实现，可被 ReAct / Plan-Execute
等策略替换。横切中间件在本主轴关键节点按序插入、被拒短路。

对应规格：doc/openspec/specs/loop/spec.md
模块设计：doc/02-modules/loop.md
"""

from .default import ActionObserver, Approver, DefaultLoop, TurnObserver
from .planner import LLMPlanner
from .protocol import (
    Action,
    ActionGroup,
    ActionResult,
    LimitsConfigurable,
    LoopContext,
    LoopEvent,
    LoopPlugin,
    LoopResult,
    Thinking,
    collect_result,
    current_session_id,
)

__all__ = [
    "Action",
    "ActionGroup",
    "ActionObserver",
    "Approver",
    "ActionResult",
    "DefaultLoop",
    "LLMPlanner",
    "LimitsConfigurable",
    "LoopContext",
    "LoopEvent",
    "LoopPlugin",
    "LoopResult",
    "Thinking",
    "TurnObserver",
    "collect_result",
    "current_session_id",
]
