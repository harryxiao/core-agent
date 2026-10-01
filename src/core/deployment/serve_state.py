"""serve 常驻进程状态（deployment）—— pidfile 探活。

serve 启动写 ``{pid, started_at}``，probe 读 pidfile 用 ``os.kill(pid, 0)`` 判活；
``pid_alive`` 可注入以便测试。文件持久化（非 HTTP 探活）：无端口/鉴权/连接失败
模式，确定性、幂等、进程内进程间一致。

对应接口：doc/03-interfaces/deployment-interface.md §4（健康探活）
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path

from .models import HealthStatus


def _pid_alive(pid: int) -> bool:
    """进程是否存在（信号 0 探测，不发送信号）。"""
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


class ServeStateStore:
    """serve 常驻状态：mark_running/mark_stopped 写状态，probe 读状态判活。"""

    def __init__(
        self,
        path: Path | None = None,
        *,
        pid_alive: Callable[[int], bool] | None = None,
    ) -> None:
        self._path = path
        self._pid_alive = pid_alive if pid_alive is not None else _pid_alive

    def mark_running(self, pid: int | None = None) -> None:
        """标记 serve 运行中（缺省用当前进程 pid）。"""
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"pid": pid if pid is not None else os.getpid(), "started_at": time.time()}),
            encoding="utf-8",
        )

    def mark_stopped(self) -> None:
        """标记 serve 已停止。"""
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"pid": None, "started_at": time.time()}), encoding="utf-8"
        )

    def probe(self) -> HealthStatus:
        """读 pidfile 判活：pid 存活 → alive；否则返回失败原因。"""
        if self._path is None or not self._path.exists():
            return HealthStatus(alive=False, detail="serve 未运行")
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            pid = data.get("pid")
        except (json.JSONDecodeError, OSError):
            return HealthStatus(alive=False, detail="serve 状态损坏")
        if not pid:
            return HealthStatus(alive=False, detail="serve 已停止")
        if self._pid_alive(pid):
            return HealthStatus(alive=True, detail=f"serve 运行中 (pid={pid})")
        return HealthStatus(alive=False, detail="serve 进程已退出")
