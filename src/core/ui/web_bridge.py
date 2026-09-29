"""Web 桥接（ui）。

HTTP + SSE 打开单 SPA；前端纯静态独立托管，经统一后端 API 连接常驻
Harness Host。HTTP/SSE 传输经 fastapi_serve 适配器落地（懒 import，MAL 隔离）。

对应接口：doc/03-interfaces/ui-interface.md §2
"""

from __future__ import annotations

from collections.abc import Callable

from .api import UIAPILayer
from .fastapi_serve import serve as _serve_fastapi


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


def _default_serve(api: UIAPILayer, host: str, port: int) -> None:
    """启动真实 FastAPI/uvicorn HTTP + SSE 服务（经 fastapi_serve 适配器）。"""
    _serve_fastapi(api, host, port)
