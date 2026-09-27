"""上下文工程领域错误（context）。

结构化错误码与异常分离：预算超限 / 信息地图失效 / 压实有损三类失败，
统一继承 :class:`ContextError`，上层按 ``code`` 分支处理。

对应接口：doc/03-interfaces/context-interface.md §6
"""

from __future__ import annotations

from enum import StrEnum


class ContextErrorCode(StrEnum):
    """上下文工程结构化错误码。"""

    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    MAP_STALE = "MAP_STALE"
    COMPACTION_LOSSY = "COMPACTION_LOSSY"


class ContextError(Exception):
    """上下文工程业务异常：携带结构化错误码与信息。"""

    def __init__(self, code: ContextErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
