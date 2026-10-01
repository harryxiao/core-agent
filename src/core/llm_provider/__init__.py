"""LLM Provider（三方大模型归一化接入）。

统一 ``LLMProvider`` 抽象接口（completion / stream / embedding 六入口），
StdlibLLMProvider（OpenAI 兼容 stdlib）作默认实现、经依赖注入隔离可替换；底层异常归一到 ``LLMError``
层级；异步为主、同步为薄壳。

对应规格：doc/openspec/specs/llm-provider/spec.md
"""

from .errors import (
    LLMAuthError,
    LLMError,
    LLMNetworkError,
    LLMRateLimitedError,
    LLMTimeoutError,
    UnknownProviderError,
)
from .models import Embedding, LLMChunk, LLMRequest, LLMResponse, Message, TokenUsage
from .provider import LLMProvider
from .registry import LLMProviderRegistry
from .stdlib_provider import StdlibLLMProvider, map_http_error

__all__ = [
    "Embedding",
    "LLMAuthError",
    "LLMChunk",
    "LLMError",
    "LLMNetworkError",
    "LLMProvider",
    "LLMProviderRegistry",
    "LLMRateLimitedError",
    "LLMRequest",
    "LLMResponse",
    "LLMTimeoutError",
    "StdlibLLMProvider",
    "Message",
    "TokenUsage",
    "UnknownProviderError",
    "map_http_error",
]
