"""embedding 生成抽象与实现（rag）。

``Embedder`` 抽象隔离 embedding 后端：生产默认 sentence-transformers + BGE
本地推理，经本抽象替换为远端模型（llm-provider 归一化入口）时调用方零改动；
离线缺省 ``HashEmbedder`` 以字符 n-gram 哈希生成确定性向量（零第三方依赖、
本地推理无外部 API），``LLMEmbedder`` 经 llm-provider 切远端模型。

对应接口：doc/03-interfaces/rag-interface.md §3 / §6
"""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

from core.llm_provider import LLMError, LLMProvider

from .errors import RAGError, RAGErrorCode


def _hash_bucket(text: str, dim: int) -> int:
    """稳定哈希映射到桶（跨进程确定，避免内建 hash 随机化）。"""
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % dim


class Embedder(ABC):
    """embedding 抽象接口：文本 → 向量。"""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """生成文本向量；本地推理无外部依赖或经 llm-provider 切远端。"""
        raise NotImplementedError


class HashEmbedder(Embedder):
    """确定性字符 n-gram 哈希向量化（零第三方依赖，本地推理）。"""

    def __init__(self, *, dim: int = 128, ngram: int = 3) -> None:
        self._dim = dim
        self._ngram = ngram

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        normalized = text.lower()
        n = len(normalized)
        grams = (
            [normalized[i : i + self._ngram] for i in range(n - self._ngram + 1)]
            if n >= self._ngram
            else ([normalized] if normalized else [])
        )
        for gram in grams:
            vec[_hash_bucket(gram, self._dim)] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


class LLMEmbedder(Embedder):
    """经 llm-provider 归一化入口生成 embedding（远端模型切换）。"""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def embed(self, text: str) -> list[float]:
        try:
            embeddings = self._provider.embedding([text])
        except LLMError as exc:
            raise RAGError(RAGErrorCode.EMBEDDING_FAILED, f"embedding 生成失败: {exc}") from exc
        return embeddings[0].vector
