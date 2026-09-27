"""CLI 运维命令面领域错误码（cli-ops）。

未识别命令、ConfigSpec map_to 非法（目标不存在或冲突）以
:class:`CliOpsError` 表达，阻断启动。

对应接口：doc/03-interfaces/cli-ops-interface.md §4
"""

from __future__ import annotations

from enum import StrEnum


class CliOpsErrorCode(StrEnum):
    """CLI 运维结构化错误码。"""

    UNKNOWN_COMMAND = "UNKNOWN_COMMAND"
    INVALID_MAP_TO = "INVALID_MAP_TO"


class CliOpsError(Exception):
    """CLI 运维业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: CliOpsErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
