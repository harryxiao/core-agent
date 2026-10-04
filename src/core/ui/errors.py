"""UI 界面领域错误码（ui）。

结构化错误码与异常分离，供 UIAPILayer 抛出。

对应接口：doc/03-interfaces/ui-interface.md §5
"""

from __future__ import annotations

from enum import StrEnum


class UiErrorCode(StrEnum):
    """UI 结构化错误码。"""

    UI_LLM_KEY_UNSET = "UI_LLM_KEY_UNSET"
    UI_SESSION_NOT_FOUND = "UI_SESSION_NOT_FOUND"
    UI_MODALITY_MISSING = "UI_MODALITY_MISSING"
    UI_BARGEIN = "UI_BARGEIN"
    UI_ORCHESTRATOR_UNSET = "UI_ORCHESTRATOR_UNSET"
    UI_PET_UNSET = "UI_PET_UNSET"


class UiError(Exception):
    """UI 业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: UiErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
