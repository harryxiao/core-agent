"""上下文工程（context，L2.5）。

动态上下文构建 + 信息地图二级索引 + 自动压实 + 预算控制；宪法分区必保注入、
项目信息未命中静默降级。原 substrate 命名已统一为 context（D2）。

对应规格：doc/openspec/specs/context/spec.md
"""

from .assembler import DynamicAssembler
from .blocks import BlockPlan, plan_blocks
from .budget import BudgetManager, estimate_tokens
from .compactor import Compactor
from .errors import ContextError, ContextErrorCode
from .info_map import InfoMap
from .models import Compaction, ContextPack, MapEntry, Pointer
from .window import WindowPlan, plan_window

__all__ = [
    "BlockPlan",
    "BudgetManager",
    "Compaction",
    "Compactor",
    "ContextError",
    "ContextErrorCode",
    "ContextPack",
    "DynamicAssembler",
    "InfoMap",
    "MapEntry",
    "Pointer",
    "WindowPlan",
    "estimate_tokens",
    "plan_blocks",
    "plan_window",
]
