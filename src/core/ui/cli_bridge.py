"""CLI 桥接（ui）。

Textual 层直连统一 API（同进程，无 IPC），不另起命令解析：运维命令面
（status/doctor/logs/install/mcp/auth/gateway）仍在 cli-ops，CLIBridge
只承载交互会话面。

对应接口：doc/03-interfaces/ui-interface.md §2
"""

from __future__ import annotations

from .api import UIAPILayer


class CLIBridge:
    """CLI 入口桥：connect 返回统一 API 层（同进程复用，无绕过）。"""

    def __init__(self, *, api: UIAPILayer | None = None) -> None:
        self._api = api if api is not None else UIAPILayer()

    def connect(self) -> UIAPILayer:
        """返回统一 API 层句柄，CLI 交互会话经此驱动内核。"""
        return self._api
