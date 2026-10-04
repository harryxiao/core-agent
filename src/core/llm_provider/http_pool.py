"""按 origin 复用长连接的传输层（llm-provider，零第三方依赖）。

规格 llm-provider「模型调用可靠性」场景「连接复用」要求「复用底层 connection / keep-alive
连接，减少握手开销，**连接失效时自动重建**」。此前三条传输路径（chat / embedding / SSE）
各自 ``urllib.request.urlopen``，**每次调用都新建连接**（无 keep-alive），本模块补上该能力。

设计要点（取舍见 ADR-0064）：

- **线程本地所有权**：空闲连接存在 ``threading.local()``，不跨线程共享 ⇒ 无需锁、无归还竞争。
  provider 的同步传输经 ``asyncio.to_thread`` / ``run_in_executor`` 落在工作线程上，
  同一线程的连续调用即可复用同一条连接。
- **代理回落**：环境为该 scheme 配了代理时不入池，交回 ``urlopen`` —— ``http.client`` 不读
  代理环境变量，回落比自实现代理隧道简单且语义等同。
- **3xx 回落**：``http.client`` 不跟随重定向，故 3xx 交回 ``urlopen``（保持既有行为）。
- **失效重建**：复用到的连接若在「发请求 / 读状态行」阶段失效（服务端空闲超时、reset、管道已断），
  关掉后用**新连接重发一次**；只在**尚未收到任何响应**时重发 ⇒ 不重复产生计费副作用。
- **读尽才复用**：响应体未读尽的连接（如 SSE 中途停止）关闭丢弃，避免半读流污染下一次请求。
"""

from __future__ import annotations

import http.client
import ssl
import threading
import urllib.error
import urllib.request
from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Protocol
from urllib.parse import urlsplit

# 重定向状态码：http.client 不跟随 ⇒ 交回 urlopen
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# 错误状态码起点：达到即归一为 HTTPError（与 urlopen 同口径）
_ERROR_STATUS_MIN = 400

# 「连接已失效」信号（仅用于**复用连接**的首次往返）：服务端空闲超时、连接重置、管道已断。
# 正常网络故障（如拒绝连接）不在此列 —— 那些应直接归一到领域异常，不重发。
_STALE_CONNECTION_ERRORS = (
    http.client.RemoteDisconnected,
    http.client.BadStatusLine,
    ConnectionResetError,
    BrokenPipeError,
)


def proxy_for(url: str) -> str | None:
    """该 URL 适用的环境代理地址（无则 None，含 ``no_proxy`` 例外）。

    沿用 stdlib 环境代理语义（``http_proxy`` / ``https_proxy`` / ``all_proxy``）；测试可替换本函数。
    """
    parts = urlsplit(url)
    address = urllib.request.getproxies().get(parts.scheme) or ""
    if not address or urllib.request.proxy_bypass(parts.hostname or ""):
        return None
    return str(address)


class HTTPTransport(Protocol):
    """传输抽象：provider 只依赖此协议，测试可注入替身（DI 接缝）。"""

    def send(
        self, request: urllib.request.Request, *, timeout: float
    ) -> AbstractContextManager[Any]:
        """发送请求并交出响应，退出时负责连接归还 / 关闭。"""
        ...


class HTTPConnectionPool:
    """线程本地、按 origin 复用 ``http.client`` 连接的同步传输。"""

    def __init__(self) -> None:
        self._local = threading.local()

    @contextmanager
    def send(
        self, request: urllib.request.Request, *, timeout: float
    ) -> Generator[Any, None, None]:
        """发送 ``request`` 并交出响应；退出时按「响应体是否读尽」决定归还还是丢弃连接。"""
        url = request.full_url
        if proxy_for(url) is not None:  # 代理环境：保留 urlopen 的代理语义，不入池
            with urllib.request.urlopen(request, timeout=timeout) as response:
                yield response
            return

        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}"
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        connection, reused = self._acquire(key, parts, timeout)
        try:
            response = self._roundtrip(connection, path, request)
        except _STALE_CONNECTION_ERRORS:
            if not reused:  # 新连接就失败 ⇒ 真故障，交给上层归一
                connection.close()
                raise
            connection.close()
            connection = self._connect(parts, timeout)
            try:
                response = self._roundtrip(connection, path, request)
            except BaseException:
                connection.close()
                raise

        if response.status in _REDIRECT_STATUSES:  # 不跟随重定向 ⇒ 交回 urlopen
            connection.close()
            with urllib.request.urlopen(request, timeout=timeout) as fallback:
                yield fallback
            return
        if response.status >= _ERROR_STATUS_MIN:  # 与 urlopen 同口径：归一为 HTTPError
            response.read()
            self._release(key, connection, drained=True)
            raise urllib.error.HTTPError(
                url, response.status, response.reason, response.headers, None
            )
        try:
            yield response
        finally:
            self._release(key, connection, drained=response.isclosed())

    # ---- 连接簿记（全部只在调用线程内访问） ----

    def _idle(self) -> dict[str, http.client.HTTPConnection]:
        """本线程的空闲连接表（lazy 建，避免线程未用过传输就留属性）。"""
        idle: dict[str, http.client.HTTPConnection] | None = getattr(self._local, "idle", None)
        if idle is None:
            idle = {}
            self._local.idle = idle
        return idle

    def _acquire(
        self, key: str, parts: Any, timeout: float
    ) -> tuple[http.client.HTTPConnection, bool]:
        connection = self._idle().pop(key, None)
        if connection is not None:
            return connection, True
        return self._connect(parts, timeout), False

    def _connect(self, parts: Any, timeout: float) -> http.client.HTTPConnection:
        host = parts.hostname or ""
        port = parts.port
        if parts.scheme == "https":
            return http.client.HTTPSConnection(
                host, port, timeout=timeout, context=ssl.create_default_context()
            )
        return http.client.HTTPConnection(host, port, timeout=timeout)

    def _release(self, key: str, connection: http.client.HTTPConnection, *, drained: bool) -> None:
        if drained:
            self._idle()[key] = connection
        else:
            connection.close()

    @staticmethod
    def _roundtrip(
        connection: http.client.HTTPConnection, path: str, request: urllib.request.Request
    ) -> http.client.HTTPResponse:
        connection.request(
            request.get_method(), path, body=request.data, headers=dict(request.headers)
        )
        return connection.getresponse()
