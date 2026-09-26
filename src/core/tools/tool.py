"""工具原子单元（tool-use）。

把「定义 + 处理器 + 撤销闭包」封装为 :class:`Tool`，处理器可为同步或异步
（Provider 统一桥接）；撤销闭包在写类工具成功执行后由 ``EffectTracker``
按 trace 逆序调用，实现时间旅行回滚。

对应接口：doc/03-interfaces/tool-use-interface.md §1 / §3
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .models import ToolDef


@dataclass
class Tool:
    """工具原子：契约定义 + 执行处理器 + 可选撤销闭包。"""

    definition: ToolDef
    handler: Callable[..., Any]
    undo: Callable[[], None] | None = None
