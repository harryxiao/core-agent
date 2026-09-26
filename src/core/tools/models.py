"""工具调用数据模型（tool-use）。

定义工具契约 / 调用结果 / 结构化错误 / 确认门决策四类数据，供
``ToolProvider`` / ``SafetyGate`` 与内核 loop 消费。

对应接口：doc/03-interfaces/tool-use-interface.md §1 / §2 / §4
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class ToolDef:
    """工具契约：schema 定义 + coeffect 副作用声明 + 可逆性。"""

    tool_id: str
    description: str
    schema: dict[str, Any]
    coeffects: list[str]
    reversible: bool
    timeout_s: float = 30.0
    max_output: int = 8192


@dataclass
class ToolResult:
    """工具调用结果：成功携数据 / 失败携结构化错误。"""

    ok: bool
    data: Any = None
    error: ToolError | None = None
    effect_id: str | None = None


@dataclass
class ToolError:
    """结构化工具错误：错误码 + 人类可读信息。"""

    code: str
    message: str
    details: dict[str, Any] | None = None


@dataclass
class GateDecision:
    """确认门决策：auto 放行 / confirm 需人工确认 / deny 拒绝。"""

    action: Literal["auto", "confirm", "deny"]
    reason: str
