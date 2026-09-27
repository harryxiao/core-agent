"""IM 网关领域错误码（im）。

结构化错误码与异常分离，供 IMGateway 抛出。

对应接口：doc/03-interfaces/im-interface.md §6
"""

from __future__ import annotations

from enum import StrEnum


class ImErrorCode(StrEnum):
    """IM 结构化错误码。"""

    IM_PLATFORM_UNSUPPORTED = "IM_PLATFORM_UNSUPPORTED"
    IM_NOT_WHITELISTED = "IM_NOT_WHITELISTED"
    IM_CONFIRM_DENIED = "IM_CONFIRM_DENIED"
    IM_CONFIRM_TIMEOUT = "IM_CONFIRM_TIMEOUT"
    IM_PLATFORM_DISCONNECTED = "IM_PLATFORM_DISCONNECTED"
    IM_SEND_FAILED = "IM_SEND_FAILED"


class ImError(Exception):
    """IM 业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: ImErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
