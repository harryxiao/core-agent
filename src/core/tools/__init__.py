"""工具使用（L1 原子工具，能力可调）。

把模型动作转化为带 schema 的可执行调用，经 coeffect 副作用契约注入约束；
写类工具走可逆效应（撤销 / 时间旅行回滚），异步为主、同步为薄壳。

对应规格：doc/openspec/specs/tool-use/spec.md
"""

from .builtin import (
    builtin_tools,
    code_run,
    context_read,
    file_patch,
    file_read,
    file_write,
    gate_run,
    process_kill,
    process_manage,
    web_fetch,
)
from .env_shell import EnvironmentSnapshot, format_env_block, probe_environment
from .errors import ToolErrorCode, ToolUseError
from .execution import ProcessRegistry
from .install_tools import StubPlugin, install_tool, list_tool, uninstall_tool
from .models import GateDecision, ToolDef, ToolError, ToolResult
from .provider import ToolProvider
from .safety_gate import SafetyGate
from .tool import Tool

__all__ = [
    "EnvironmentSnapshot",
    "GateDecision",
    "ProcessRegistry",
    "SafetyGate",
    "StubPlugin",
    "Tool",
    "ToolDef",
    "ToolError",
    "ToolErrorCode",
    "ToolProvider",
    "ToolResult",
    "ToolUseError",
    "builtin_tools",
    "code_run",
    "context_read",
    "file_patch",
    "file_read",
    "file_write",
    "format_env_block",
    "gate_run",
    "web_fetch",
    "install_tool",
    "list_tool",
    "probe_environment",
    "process_kill",
    "process_manage",
    "uninstall_tool",
]
