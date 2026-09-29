"""决策领域错误码（judgment）。

结构化错误码与异常分离：``JUDGMENT_PROVIDER_UNREACHABLE`` / ``JUDGMENT_TIMEOUT`` /
``JUDGMENT_LOW_CONFIDENCE`` 为回退触发信号（被 DecisionRouter 捕获转为回退），
``JUDGMENT_SCHEMA_MISMATCH`` / ``JUDGMENT_INVALID_PRIMITIVE`` 为契约违约，向调用方抛出。

对应接口：doc/03-interfaces/judgment-interface.md §6
"""

from __future__ import annotations

from enum import StrEnum


class JudgmentErrorCode(StrEnum):
    """决策结构化错误码。"""

    JUDGMENT_PROVIDER_UNREACHABLE = "JUDGMENT_PROVIDER_UNREACHABLE"
    JUDGMENT_SCHEMA_MISMATCH = "JUDGMENT_SCHEMA_MISMATCH"
    JUDGMENT_LOW_CONFIDENCE = "JUDGMENT_LOW_CONFIDENCE"
    JUDGMENT_TIMEOUT = "JUDGMENT_TIMEOUT"
    JUDGMENT_INVALID_PRIMITIVE = "JUDGMENT_INVALID_PRIMITIVE"


class JudgmentError(Exception):
    """决策业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: JudgmentErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
