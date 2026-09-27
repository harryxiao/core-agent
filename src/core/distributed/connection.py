"""A2A 连接管理（distributed）。

管理对等连接的完整生命周期：心跳保活（heartbeat）、断线自动重连（指数退避）、
调用超时判定、显式资源释放（release）。时钟经构造注入，便于测试控制。

对应接口：doc/03-interfaces/distributed-interface.md ｜ 规格「A2A 连接管理」
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class ConnectionState(StrEnum):
    """连接状态。"""

    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"
    CLOSED = "closed"


@dataclass
class Connection:
    """一条对等连接。"""

    peer: str
    state: ConnectionState = ConnectionState.CONNECTED
    failures: int = 0
    last_seen: float = 0.0


class ConnectionManager:
    """对等连接生命周期管理：心跳 / 重连 / 超时 / 释放。"""

    def __init__(
        self,
        *,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._connections: dict[str, Connection] = {}
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._clock = clock if clock is not None else time.monotonic

    def connect(self, peer: str) -> Connection:
        """建立（或重置）对等连接。"""
        conn = self._connections.setdefault(peer, Connection(peer=peer))
        conn.state = ConnectionState.CONNECTED
        conn.failures = 0
        conn.last_seen = self._clock()
        return conn

    def connection(self, peer: str) -> Connection | None:
        """按名取连接。"""
        return self._connections.get(peer)

    def heartbeat(self, peer: str) -> bool:
        """心跳保活：刷新最后活跃时间。"""
        conn = self._connections.get(peer)
        if conn is None or conn.state is ConnectionState.CLOSED:
            return False
        conn.last_seen = self._clock()
        return True

    def is_alive(self, peer: str, timeout: float) -> bool:
        """判定连接是否仍活跃（未超过超时阈值）。"""
        conn = self._connections.get(peer)
        if conn is None or conn.state is ConnectionState.CLOSED:
            return False
        return self._clock() - conn.last_seen <= timeout

    def reconnect(self, peer: str) -> Connection:
        """断线重连：累计失败次数，超过上限标记断连，否则进入重连（指数退避）。"""
        conn = self._connections.get(peer)
        if conn is None:
            return self.connect(peer)
        conn.failures += 1
        if conn.failures > self._max_retries:
            conn.state = ConnectionState.DISCONNECTED
        else:
            conn.state = ConnectionState.RECONNECTING
        return conn

    def backoff(self, peer: str) -> float:
        """指数退避间隔（按累计失败次数）。"""
        conn = self._connections.get(peer)
        if conn is None or conn.failures <= 0:
            return 0.0
        return self._backoff_base * (2 ** (conn.failures - 1))

    def release(self, peer: str) -> None:
        """显式释放连接资源（内存态标记 CLOSED）。"""
        conn = self._connections.get(peer)
        if conn is not None:
            conn.state = ConnectionState.CLOSED

    def active_peers(self) -> list[str]:
        """枚举未关闭的连接对端。"""
        return [
            peer
            for peer, conn in self._connections.items()
            if conn.state is not ConnectionState.CLOSED
        ]
