"""文档化记忆（notes）结构化错误码。

对应规格：doc/openspec/specs/notes/spec.md
接口设计：doc/03-interfaces/notes-interface.md §4
"""

from __future__ import annotations

from enum import StrEnum


class NoteErrorCode(StrEnum):
    """文档化记忆结构化错误码。"""

    NOTE_NOT_FOUND = "NOTE_NOT_FOUND"
    TOPIC_EXISTS = "TOPIC_EXISTS"


class NoteError(Exception):
    """文档化记忆业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: NoteErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
