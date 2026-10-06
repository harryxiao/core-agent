"""CLI 桥接（ui）。

connect 进入 Textual 交互会话循环（无子命令），不另起命令解析：运维命令面
（status/doctor/logs/install/mcp/auth/gateway）仍在 cli-ops，CLIBridge
只承载交互会话面。Textual 经 repl 适配器落地（懒 import，MAL 隔离）。

对应接口：doc/03-interfaces/ui-interface.md §2
"""

from __future__ import annotations

from collections.abc import Callable

from .api import UIAPILayer
from .repl import run_repl as _run_repl


class CLIBridge:
    """CLI 入口桥：connect 进入 Textual 交互会话循环（无子命令）。"""

    def __init__(
        self,
        *,
        api: UIAPILayer | None = None,
        connect_impl: Callable[[UIAPILayer, str], None] | None = None,
        session_id: str = "",
    ) -> None:
        self._api = api if api is not None else UIAPILayer()
        self._connect_impl = connect_impl if connect_impl is not None else _default_connect
        self._session_id = session_id

    def connect(self) -> None:
        """进入交互会话循环（真实 Textual 循环经 connect_impl 注入；非空会话标识 ⇒ 续聊）。"""
        self._connect_impl(self._api, self._session_id)


def _default_connect(api: UIAPILayer, session_id: str = "") -> None:
    """启动真实 Textual 交互会话循环（经 repl 适配器）。"""
    _run_repl(api, session_id)
