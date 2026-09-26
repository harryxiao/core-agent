"""权限领域错误码（permission）。

结构化错误码与异常分离。注：异常类命名为 :class:`AccessControlError` 而非
``PermissionError``，避免遮蔽内建 ``PermissionError``（OSError 子类）。

对应接口：doc/03-interfaces/permission-interface.md §5
"""

from __future__ import annotations

from enum import StrEnum


class PermissionErrorCode(StrEnum):
    """权限结构化错误码。"""

    PERMISSION_DENIED = "PERMISSION_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_TIMEOUT = "APPROVAL_TIMEOUT"
    SANDBOX_UNAVAILABLE = "SANDBOX_UNAVAILABLE"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"


class AccessControlError(Exception):
    """权限业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: PermissionErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
