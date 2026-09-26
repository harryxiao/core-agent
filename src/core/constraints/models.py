"""约束中间件数据模型（constraints）。

定义洋葱管道执行所需的执行上下文 / 请求 / 响应 / 解析结果四类数据，
供 :class:`Middleware` 与 :class:`Pipeline` 消费。

对应接口：doc/03-interfaces/constraints-interface.md §1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecContext:
    """执行上下文：贯穿一条执行链路的轻量载体。"""

    trace_id: str
    payload: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass
class ExecRequest:
    """输入侧请求：工具名 + 参数 + schema + 追溯 id。"""

    tool: str
    args: dict[str, Any]
    schema: dict[str, Any]
    trace_id: str


@dataclass
class ExecResponse:
    """输出侧响应：成功携数据 / 失败携错误码。"""

    ok: bool
    data: Any = None
    error: str | None = None
    effect_id: str | None = None


@dataclass
class ParsedOutput:
    """自由文本解析为结构化指令的结果。"""

    ok: bool
    instruction: dict[str, Any] | None = None
    error: str | None = None
