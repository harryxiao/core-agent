"""技能领域错误码（skills）。

结构化错误码与异常分离：注册期非法定义抛 :class:`SkillError`（异常），
路由无匹配返回空列表（不抛异常），前置条件不满足返回 False（由调用方
拒绝并携带 PRECONDITION_FAILED）。

对应接口：doc/03-interfaces/skills-interface.md §8
"""

from __future__ import annotations

from enum import StrEnum


class SkillErrorCode(StrEnum):
    """技能结构化错误码。"""

    INVALID_SKILL_SCHEMA = "INVALID_SKILL_SCHEMA"
    NO_SKILL_MATCH = "NO_SKILL_MATCH"
    PRECONDITION_FAILED = "PRECONDITION_FAILED"


class SkillError(Exception):
    """技能业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: SkillErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
