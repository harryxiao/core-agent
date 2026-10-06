"""对话会话注册表（SessionRegistry）。

统一 API 层创建 / 校验会话标识的事实来源；可落盘（注入 ``path``）⇒ CLI / Web /
Desktop 三入口（含各自独立进程）共享同一注册表。缺省 ``path=None`` 纯内存
（后向兼容既有进程内语义）。

采用**读透 + 写时合并**（非「ctor 载入一次」）：``exists`` / ``list`` 每次读回磁盘，
``create`` 先读回磁盘再合并写回 —— 以支持「长驻进程见到他进程（CLI）新建的会话」；
创建用**进程内互斥**（``RLock``）保护，使同进程多线程并发创建不相互覆盖。
**跨进程**同刻并发创建不受此保护（进程内互斥不跨进程，属已知局限）。注册表为派生状态，
文件缺失 / 损坏 ⇒ 空态启动（不阻断）。

对应接口：doc/03-interfaces/ui-interface.md §1.2
"""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import cast

from core.persistence import read_state, write_state

_VERSION = 1


class SessionRegistry:
    """会话标识注册表：``{session_id: {mode, created_at}}``；``path=None`` ⇒ 纯内存。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._memory: dict[str, dict[str, object]] = {}
        self._lock = threading.RLock()

    def create(self, mode: str) -> str:
        """新建会话（读回 → 合并 → 写回），返回 session_id（进程内互斥）。"""
        with self._lock:
            session_id = uuid.uuid4().hex
            sessions = self._read()
            sessions[session_id] = {"mode": mode, "created_at": time.time()}
            self._memory = sessions
            write_state(self._path, {"version": _VERSION, "sessions": sessions})
            return session_id

    def exists(self, session_id: str) -> bool:
        """会话是否已登记（读透磁盘）。"""
        return session_id in self._read()

    def list(self) -> list[dict[str, object]]:
        """全部会话条目 ``{session_id, mode, created_at}``（读透磁盘）。"""
        return [{"session_id": session_id, **entry} for session_id, entry in self._read().items()]

    # ---- 内部 ----

    def _read(self) -> dict[str, dict[str, object]]:
        """读回全量会话表；``path=None`` 用内存副本，缺失 / 损坏 → 空表（不抛）。"""
        if self._path is None:
            return dict(self._memory)
        raw = read_state(self._path)
        if not isinstance(raw, dict):
            return {}
        sessions = cast("dict[str, object]", raw).get("sessions")
        if not isinstance(sessions, dict):
            return {}
        table = cast("dict[str, dict[str, object]]", sessions)
        return {str(key): entry for key, entry in table.items()}
