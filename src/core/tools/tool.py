"""工具原子单元（tool-use）。

把「定义 + 处理器 + 撤销闭包」封装为 :class:`Tool`，处理器可为同步或异步
（Provider 统一桥接）；写类工具成功执行后由调用方**按次**取其撤销闭包（绑定该次
写入前的快照）、记录为可逆效应，``EffectTracker`` 按 trace 逆序调用，实现时间旅行
回滚（change 0129 / E64：多次调用**各持独立快照**，回滚不串）。

对应接口：doc/03-interfaces/tool-use-interface.md §1 / §3
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .models import ToolDef


@dataclass
class Tool:
    """工具原子：契约定义 + 执行处理器 + 可选撤销闭包**工厂**。

    ``undo`` 是**按次生成**的工厂（change 0129 / E64）：每次成功执行后由调用方取一次，
    所得闭包绑定**该次**写入前的快照 ⇒ 同一工具实例跨多次调用的快照**各持独立**，
    撤销第 N 次恢复该次内容、不被后续调用覆写（``Callable[[], Callable[[], None]]``）。
    """

    definition: ToolDef
    handler: Callable[..., Any]
    undo: Callable[[], Callable[[], None]] | None = None
