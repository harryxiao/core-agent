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
    # 索引向量维度与当前 embedding 不一致（更换后端后沿用旧索引）⇒ 拒绝并提示重建
    INDEX_CORRUPT = "INDEX_CORRUPT"
    REBUILD_FAILED = "REBUILD_FAILED"
    # 检索增强生成未装配生成器（服务层无 llm-provider 通路）⇒ fail-closed，不静默给空答案
    GENERATION_UNAVAILABLE = "GENERATION_UNAVAILABLE"


class RAGError(Exception):
    """RAG 业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: RAGErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
