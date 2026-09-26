"""约束领域错误码（constraints）。

结构化错误码与异常分离：解析 / 熔断 / 重试 / 回滚四类失败均抛
:class:`ConstraintError`，上层按 ``code`` 分支处理，不向模型抛裸异常。

对应接口：doc/03-interfaces/constraints-interface.md §6
"""

from __future__ import annotations

from enum import StrEnum


class ConstraintErrorCode(StrEnum):
    """约束结构化错误码。"""

    OUTPUT_PARSE_FAILED = "OUTPUT_PARSE_FAILED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"


class ConstraintError(Exception):
    """约束业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: ConstraintErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
