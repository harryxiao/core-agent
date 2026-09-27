"""CLI 运维命令面数据模型（cli-ops）。

定义命令分组（六组），供 CLICommandDispatcher 路由。

对应接口：doc/03-interfaces/cli-ops-interface.md §1
"""

from __future__ import annotations

from enum import StrEnum


class CommandGroup(StrEnum):
    """命令分组（六组）。"""

    LIFECYCLE = "lifecycle"  # start / stop / restart / kill
    STATUS = "status"  # status / doctor / logs / version / help
    ASSET = "asset"  # install / uninstall / list / info
    CONNECTION = "connection"  # mcp add / mcp remove / mcp list
    SECURITY = "security"  # auth / permission-mode
    GATEWAY = "gateway"  # gateway
