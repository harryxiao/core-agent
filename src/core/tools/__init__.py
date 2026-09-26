"""工具使用（L1 原子工具，能力可调）。

把模型动作转化为带 schema 的可执行调用，经 coeffect 副作用契约注入约束；
写类工具走可逆效应（撤销 / 时间旅行回滚），异步为主、同步为薄壳。

对应规格：doc/openspec/specs/tool-use/spec.md
"""

from .builtin import file_patch, file_read, file_write
from .errors import ToolErrorCode, ToolUseError
from .models import GateDecision, ToolDef, ToolError, ToolResult
from .provider import ToolProvider
from .safety_gate import SafetyGate
from .tool import Tool

__all__ = [
    "GateDecision",
    "SafetyGate",
    "Tool",
    "ToolDef",
    "ToolError",
    "ToolErrorCode",
    "ToolProvider",
    "ToolResult",
    "ToolUseError",
    "file_patch",
    "file_read",
    "file_write",
]
