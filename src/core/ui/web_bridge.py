"""Web 桥接（ui）。

HTTP + SSE 打开单 SPA；前端纯静态独立托管，经统一后端 API 连接常驻
Harness Host。HTTP/SSE 传输为抽象（真实 FastAPI 后端未接）。

对应接口：doc/03-interfaces/ui-interface.md §2
"""

from __future__ import annotations

from collections.abc import Callable

from .api import UIAPILayer


class WebBridge:
    """Web 入口桥：serve 暴露统一后端 API（HTTP + SSE）。"""

    def __init__(
        self,
        *,
        api: UIAPILayer | None = None,
        serve_impl: Callable[[UIAPILayer, str, int], None] | None = None,
    ) -> None:
        self._api = api if api is not None else UIAPILayer()
        self._serve_impl = serve_impl if serve_impl is not None else _default_serve

    def serve(self, host: str, port: int) -> None:
        """启动 HTTP + SSE 服务（真实服务器经 serve_impl 注入）。"""
        self._serve_impl(self._api, host, port)


def _default_serve(_api: UIAPILayer, host: str, port: int) -> None:
    raise RuntimeError(f"HTTP/SSE 服务器未接（{host}:{port} 需接真实 FastAPI 后端）")  # noqa: TRY003
