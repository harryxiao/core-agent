"""技能市场领域错误码（skillhub）。

结构化错误码与异常分离：下载签名校验失败、来源不可达/不存在、发布被驳回、
技能未激活等场景以 :class:`SkillHubError` 表达。

对应接口：doc/03-interfaces/skillhub-interface.md §6
"""

from __future__ import annotations

from enum import StrEnum


class SkillHubErrorCode(StrEnum):
    """技能市场结构化错误码。"""

    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    SOURCE_UNHEALTHY = "SOURCE_UNHEALTHY"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    PUBLISH_REJECTED = "PUBLISH_REJECTED"
    SKILL_NOT_ACTIVE = "SKILL_NOT_ACTIVE"


class SkillHubError(Exception):
    """技能市场业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: SkillHubErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
