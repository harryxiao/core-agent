"""部署与托管领域错误码（deployment）。

结构化错误码与异常分离：升级失败 / 回滚失败 / 探活异常 / 生命周期未就绪，
以领域异常承载，不向模型抛裸异常。

对应接口：doc/03-interfaces/deployment-interface.md §错误码
"""

from __future__ import annotations

from enum import StrEnum


class DeploymentErrorCode(StrEnum):
    """部署与托管结构化错误码。"""

    UPGRADE_FAILED = "UPGRADE_FAILED"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    HEALTH_UNHEALTHY = "HEALTH_UNHEALTHY"
    NOT_READY = "NOT_READY"


class DeploymentError(Exception):
    """部署与托管业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: DeploymentErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
