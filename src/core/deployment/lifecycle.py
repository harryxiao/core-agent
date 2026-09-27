"""健康检查与生命周期（deployment）。

start / stop / restart / probe 生命周期操作；probe 暴露健康探活端点，restart 后
探活仍异常抛 HEALTH_UNHEALTHY（恢复失败）；非法迁移抛 NOT_READY。

对应接口：doc/03-interfaces/deployment-interface.md §4
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from .errors import DeploymentError, DeploymentErrorCode
from .models import HealthStatus


class LifecycleState(StrEnum):
    """生命周期状态。"""

    STOPPED = "stopped"
    STARTED = "started"
    RESTARTING = "restarting"


class LifecycleController:
    """生命周期控制 + 健康探活。"""

    def __init__(self, *, probe_fn: Callable[[], HealthStatus] | None = None) -> None:
        self._probe_fn: Callable[[], HealthStatus] = (
            probe_fn if probe_fn is not None else lambda: HealthStatus(alive=True)
        )
        self._state = LifecycleState.STOPPED

    @property
    def state(self) -> LifecycleState:
        """当前生命周期状态。"""
        return self._state

    def start(self) -> None:
        """启动（仅从 STOPPED 迁移）。"""
        self._require(LifecycleState.STOPPED)
        self._state = LifecycleState.STARTED

    def stop(self) -> None:
        """停止（仅从 STARTED 迁移）。"""
        self._require(LifecycleState.STARTED)
        self._state = LifecycleState.STOPPED

    def restart(self) -> None:
        """重启；重启后探活仍异常抛 HEALTH_UNHEALTHY（恢复失败）。"""
        self._require(LifecycleState.STARTED)
        self._state = LifecycleState.RESTARTING
        self._state = LifecycleState.STARTED
        if not self._probe_fn().alive:
            raise DeploymentError(
                DeploymentErrorCode.HEALTH_UNHEALTHY,
                "重启后探活仍异常，恢复失败",
            )

    def probe(self) -> HealthStatus:
        """健康探活端点：返回探活结果（异常由调用方触发告警/恢复）。"""
        return self._probe_fn()

    def _require(self, expected: LifecycleState) -> None:
        if self._state is not expected:
            raise DeploymentError(
                DeploymentErrorCode.NOT_READY,
                f"生命周期处于 {self._state.value}，需先 {expected.value}",
            )
