"""UI 界面数据模型（ui）。

SSE 流式事件（对齐接口 §1.1 六事件）。

对应接口：doc/03-interfaces/ui-interface.md §1.1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Event:
    """流式事件：type 取 session.created / loop.perception / loop.reasoning /
    loop.action / loop.delta / loop.result / loop.error 之一。

    ``loop.delta`` 为**流式增量**专类型（载荷 ``{"text": …}``），与**终态** ``loop.result``
    （载荷完整结果）分型（change `0132` / ADR-0125 / 账本 E65）。"""

    type: str
    payload: Any = None
