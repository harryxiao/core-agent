"""RAG 领域错误码（rag）。

结构化错误码与异常分离：摄取 / 重建 / embedding 失败以领域异常承载，
调用方据错误码降级（旧索引 / 纯 LLM 生成），不向模型抛裸异常。

对应接口：doc/03-interfaces/rag-interface.md §7
"""

from __future__ import annotations

from enum import StrEnum


class RAGErrorCode(StrEnum):
    """RAG 结构化错误码。"""

    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    # 预留：sqlite-vec 生产实现落地时使用（当前内存实现无损坏场景）
    INDEX_CORRUPT = "INDEX_CORRUPT"
    REBUILD_FAILED = "REBUILD_FAILED"


class RAGError(Exception):
    """RAG 业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: RAGErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
