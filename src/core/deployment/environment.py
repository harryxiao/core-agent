"""运行环境抽象（deployment）。

只描述运行环境抽象（进程级或容器级），不锁定具体选型：configure（读取声明式
配置）→ assemble（依赖装配）→ bootstrap（启动引导）。状态机非法迁移抛 NOT_READY。

对应接口：doc/03-interfaces/deployment-interface.md §1
"""

from __future__ import annotations

from enum import StrEnum

from .errors import DeploymentError, DeploymentErrorCode
from .models import RuntimeConfig


class EnvironmentState(StrEnum):
    """运行环境状态。"""

    NEW = "new"
    CONFIGURED = "configured"
    ASSEMBLED = "assembled"
    BOOTSTRAPPED = "bootstrapped"


class RuntimeEnvironment:
    """运行环境抽象：配置 → 装配 → 引导。"""

    def __init__(self) -> None:
        self._state = EnvironmentState.NEW
        self._config: RuntimeConfig | None = None

    @property
    def state(self) -> EnvironmentState:
        """当前环境状态。"""
        return self._state

    @property
    def config(self) -> RuntimeConfig | None:
        """已装配的声明式配置。"""
        return self._config

    def configure(self, config: RuntimeConfig) -> None:
        """读取声明式配置，装配环境。"""
        self._config = config
        self._state = EnvironmentState.CONFIGURED

    def assemble(self) -> None:
        """依赖装配（进程级或容器级）。"""
        self._require(EnvironmentState.CONFIGURED)
        self._state = EnvironmentState.ASSEMBLED

    def bootstrap(self) -> None:
        """启动引导，拉起 Core-Agent 及子模块。"""
        self._require(EnvironmentState.ASSEMBLED)
        self._state = EnvironmentState.BOOTSTRAPPED

    def _require(self, expected: EnvironmentState) -> None:
        if self._state is not expected:
            raise DeploymentError(
                DeploymentErrorCode.NOT_READY,
                f"环境处于 {self._state.value}，需先 {expected.value}",
            )
