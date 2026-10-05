"""桌面桥接（ui）。

Tauri 壳复用同一 SPA + sidecar 拉起 Python 后端；与 Web 100% 一致。
sidecar 派生的**唯一**实现点在 `_default_start`（壳只负责开窗口 / 挂 SPA）。

对应接口：doc/03-interfaces/ui-interface.md §2
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from functools import partial

from .api import UIAPILayer
from .errors import UiError, UiErrorCode

_DEFAULT_PORT = 8000
_DEFAULT_HOST = "127.0.0.1"


class DesktopBridge:
    """桌面入口桥：start_sidecar 拉起本地后端。"""

    def __init__(
        self,
        *,
        api: UIAPILayer | None = None,
        start_impl: Callable[[UIAPILayer], None] | None = None,
        port: int = _DEFAULT_PORT,
    ) -> None:
        self._api = api if api is not None else UIAPILayer()
        self._start_impl = (
            start_impl if start_impl is not None else partial(_default_start, port=port)
        )

    def start_sidecar(self) -> None:
        """拉起本地后端 sidecar（真实 sidecar 经 start_impl 注入）。"""
        self._start_impl(self._api)


def _default_start(_api: UIAPILayer, *, port: int = _DEFAULT_PORT) -> None:
    """spawn 本地后端进程（change `0100`，账本 C8 代码半）。

    列表形式传 argv ⇒ 不经 shell 解释（无注入面）；用 ``sys.executable`` 而非字面量
    ``python`` ⇒ sidecar 与被拉起方**同解释器**（venv 下 ``python`` 未必是同一个）。
    spawn 失败（可执行体缺失等）归一为 `UiError`，不静默成功。
    """
    argv = [
        sys.executable,
        "-m",
        "core.entry",
        "serve",
        "--host",
        _DEFAULT_HOST,
        "--port",
        str(port),
    ]
    try:
        subprocess.Popen(argv)  # noqa: S603 — 固定 argv、不经 shell、目标即本仓 CLI
    except OSError as exc:
        raise UiError(UiErrorCode.UI_SIDECAR_FAILED, f"sidecar 拉起失败：{exc}") from exc
