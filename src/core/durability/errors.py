"""持久化领域错误码（durability）。

结构化错误码与异常分离，注册期 / 结构性失败抛异常，调用期失败尽量以结果
对象或降级标记承载。

对应接口：doc/03-interfaces/durability-interface.md §6
"""

from __future__ import annotations

from enum import StrEnum


class DurabilityErrorCode(StrEnum):
    """持久化结构化错误码。"""

    CHECKPOINT_NOT_FOUND = "CHECKPOINT_NOT_FOUND"
    CHECKPOINT_CORRUPT = "CHECKPOINT_CORRUPT"
    RESTORE_DEGRADED = "RESTORE_DEGRADED"
    RETENTION_QUOTA_EXCEEDED = "RETENTION_QUOTA_EXCEEDED"


class DurabilityError(Exception):
    """持久化业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: DurabilityErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
