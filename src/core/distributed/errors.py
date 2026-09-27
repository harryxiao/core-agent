"""分布式协作领域错误码（distributed）。

结构化错误码与异常分离：对端不可达 / 卡片无效 / 协议不支持 / 越权 / 鉴权失败 /
任务失败，以领域异常承载，不向模型抛裸异常。

对应接口：doc/03-interfaces/distributed-interface.md §6
"""

from __future__ import annotations

from enum import StrEnum


class DistributedErrorCode(StrEnum):
    """分布式协作结构化错误码。"""

    A2A_PEER_UNREACHABLE = "A2A_PEER_UNREACHABLE"
    A2A_CARD_INVALID = "A2A_CARD_INVALID"
    A2A_PROTOCOL_UNSUPPORTED = "A2A_PROTOCOL_UNSUPPORTED"
    A2A_SCOPE_DENIED = "A2A_SCOPE_DENIED"
    A2A_AUTH_FAILED = "A2A_AUTH_FAILED"
    A2A_TASK_FAILED = "A2A_TASK_FAILED"


class DistributedError(Exception):
    """分布式协作业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: DistributedErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
