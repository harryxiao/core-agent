"""Harness Host 常驻服务（deployment）。

单一 Host 进程常驻承载内核，作为统一接入端点；多个客户端并发接入、各自建立
独立会话（互不串扰）。连接生命周期状态机：accept → 断线清理（disconnect）→
超时回收（reap）。时钟经构造注入，便于测试控制。

对应接口：doc/03-interfaces/deployment-interface.md §6 ｜ 规格「客户端断线与会话清理」
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from .models import ClientConnection, Session, SessionState


class HarnessHost:
    """常驻 Host：多客户端接入统一端点 + 会话生命周期管理。"""

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        path: Path | None = None,
    ) -> None:
        self._clock = clock if clock is not None else time.monotonic
        self._sessions: dict[str, Session] = {}
        self._serving = False
        self._counter = 0
        self._path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                self._load()

    @property
    def serving(self) -> bool:
        """是否处于常驻服务状态。"""
        return self._serving

    def serve(self) -> None:
        """常驻运行，承载内核并对外暴露统一接入端点。"""
        self._serving = True

    def accept(self, client: ClientConnection) -> Session:
        """客户端接入，建立独立会话。"""
        self._counter += 1
        session = Session(
            session_id=f"session-{self._counter}",
            client_id=client.client_id,
            state=SessionState.CONNECTED,
            last_seen=self._clock(),
        )
        self._sessions[session.session_id] = session
        self._persist()
        return session

    def sessions(self) -> list[Session]:
        """枚举当前接入的活跃会话（断线/超时已回收的不在内，互不串扰）。"""
        return [
            session
            for session in self._sessions.values()
            if session.state is not SessionState.DISCONNECTED
            and session.state is not SessionState.EXPIRED
        ]

    def disconnect(self, session_id: str) -> None:
        """客户端断线清理：标记会话断线，不影响其他并发客户端。"""
        session = self._sessions.get(session_id)
        if session is not None:
            session.state = SessionState.DISCONNECTED
            self._persist()

    def reap(self, timeout: float) -> list[str]:
        """连接超时回收：回收超过超时阈值未活动的会话，返回回收的 session_id。"""
        now = self._clock()
        expired: list[str] = []
        for session_id, session in self._sessions.items():
            if session.state is SessionState.CONNECTED and now - session.last_seen > timeout:
                session.state = SessionState.EXPIRED
                expired.append(session_id)
        if expired:
            self._persist()
        return expired

    # ---- 持久化 ----

    def _persist(self) -> None:
        if self._path is None:
            return
        lines = [json.dumps(asdict(s), ensure_ascii=False) for s in self._sessions.values()]
        self._path.write_text("\n".join(lines), encoding="utf-8")

    def _load(self) -> None:
        if self._path is None:
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                session = Session(
                    session_id=data["session_id"],
                    client_id=data["client_id"],
                    state=SessionState(data["state"]),
                    last_seen=float(data["last_seen"]),
                )
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            self._sessions[session.session_id] = session
        self._counter = max(
            (int(sid.rsplit("-", 1)[1]) for sid in self._sessions if sid.startswith("session-")),
            default=0,
        )
