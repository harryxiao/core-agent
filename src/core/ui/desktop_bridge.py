"""桌面桥接（ui）。

Tauri 壳复用同一 SPA + sidecar 拉起 Python 后端；与 Web 100% 一致。
sidecar 拉起为抽象（真实 Tauri 壳未接）。

对应接口：doc/03-interfaces/ui-interface.md §2
"""

from __future__ import annotations

from collections.abc import Callable

from .api import UIAPILayer


class DesktopBridge:
    """桌面入口桥：start_sidecar 拉起本地后端。"""

    def __init__(
        self,
        *,
        api: UIAPILayer | None = None,
        start_impl: Callable[[UIAPILayer], None] | None = None,
    ) -> None:
        self._api = api if api is not None else UIAPILayer()
        self._start_impl = start_impl if start_impl is not None else _default_start

    def start_sidecar(self) -> None:
        """拉起本地后端 sidecar（真实 sidecar 经 start_impl 注入）。"""
        self._start_impl(self._api)


def _default_start(_api: UIAPILayer) -> None:
    raise RuntimeError("sidecar 拉起未接（需接真实 Tauri 壳 + sidecar）")  # noqa: TRY003
