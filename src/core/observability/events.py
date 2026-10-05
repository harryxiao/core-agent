"""可观测性事件模型（TraceEvent）。

对应接口：doc/03-interfaces/observability-interface.md §1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TraceEvent:
    """一条结构化遥测事件（脱敏后内容）。"""

    trace_id: str  # 单任务全链路 id
    span_id: str  # 单步 span id
    ts: float
    kind: str  # "model_io" | "tool_call" | "effect" | "metric" | 模块失败留痕（如 loop_finished）
    payload: dict[str, Any] = field(default_factory=dict[str, Any])
    # 模块归因：产生该事件的**架构模块** id（如 "loop.default"），供按模块聚合与缺陷归因；
    # 缺省为空表示未归因（向后兼容，既有四类 kind 路径不受影响）。
    module_id: str | None = None
