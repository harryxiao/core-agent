"""可观测性领域错误（observability）。

遥测故障**绝不阻塞主循环**：导出失败降级为内存缓冲异步落盘，仅在
缓冲溢出等兜底场景以结构化错误码暴露，供告警规则评估，不向调用方抛裸异常。

对应接口：doc/03-interfaces/observability-interface.md §6
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """可观测性结构化错误码。"""

    EXPORT_FAILED = "EXPORT_FAILED"
    TELEMETRY_DEGRADED = "TELEMETRY_DEGRADED"


class TelemetryError(Exception):
    """遥测业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
