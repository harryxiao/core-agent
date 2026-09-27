"""CI/CD 交付流水线领域错误码（ci-cd）。

结构化错误码与异常分离，供 CICDPipeline / ArtifactPublisher 抛出。

对应接口：doc/03-interfaces/ci-cd-interface.md §4
"""

from __future__ import annotations

from enum import StrEnum


class CiCdErrorCode(StrEnum):
    """CI/CD 结构化错误码。"""

    GATE_FAILED = "GATE_FAILED"
    ARTIFACT_NOT_FOUND = "ARTIFACT_NOT_FOUND"
    CHANNEL_UNREACHABLE = "CHANNEL_UNREACHABLE"


class CiCdError(Exception):
    """CI/CD 业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: CiCdErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
