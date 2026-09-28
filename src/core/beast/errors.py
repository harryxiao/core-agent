"""神兽模式领域错误码（beast-mode）。

结构化错误码与异常分离，供 BeastSession / BeastManager 抛出。
未知神兽复用 orchestration 的 ``NO_AGENT_MATCH``（召唤即 handoff）。

对应接口：doc/03-interfaces/beast-mode-interface.md §5
"""

from __future__ import annotations

from enum import StrEnum


class BeastErrorCode(StrEnum):
    """神兽模式结构化错误码。"""

    BEAST_ALREADY_MANIFEST = "BEAST_ALREADY_MANIFEST"  # 同兽重复召唤（兽内串行）
    BEAST_NOT_MANIFEST = "BEAST_NOT_MANIFEST"  # 召回/激活无在岗兽
    BEAST_MEMORY_WRITE_FAILED = "BEAST_MEMORY_WRITE_FAILED"  # 独立记忆写入失败


class BeastError(Exception):
    """神兽模式业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: BeastErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
