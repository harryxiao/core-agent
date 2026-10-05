"""宠物模式领域错误码（pet-core）。

结构化错误码与异常分离，供 PetSession / PetActivator / PetManager 抛出。

对应接口：doc/03-interfaces/pet-mode-interface.md §5
"""

from __future__ import annotations

from enum import StrEnum


class PetErrorCode(StrEnum):
    """宠物模式结构化错误码。"""

    PET_ALREADY_ACTIVE = "PET_ALREADY_ACTIVE"
    PET_NOT_ACTIVE = "PET_NOT_ACTIVE"
    PET_NOT_FOUND = "PET_NOT_FOUND"
    PET_TARGET_AMBIGUOUS = "PET_TARGET_AMBIGUOUS"
    PET_BACKOFF = "PET_BACKOFF"
    PET_YIELDING = "PET_YIELDING"
    PET_PREFERENCE_WRITE_FAILED = "PET_PREFERENCE_WRITE_FAILED"


class PetError(Exception):
    """宠物模式业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: PetErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
