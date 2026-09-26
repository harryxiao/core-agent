"""LLM 领域异常层级（llm-provider）。

把底层供应商超时 / 限流 / 鉴权 / 网络异常统一归一到本层级，上层只处理
一类错误语义，不泄漏三方原始异常结构（ADR：错误归一化）。

对应接口：doc/03-interfaces/llm-provider-interface.md §5
"""

from __future__ import annotations


class LLMError(Exception):
    """LLM 调用领域异常基类。上层只捕获此类语义。"""

    code = "LLM_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class LLMTimeoutError(LLMError):
    """调用超时。"""

    code = "LLM_TIMEOUT"


class LLMRateLimitedError(LLMError):
    """限流（可重试）。"""

    code = "LLM_RATE_LIMITED"


class LLMAuthError(LLMError):
    """鉴权失败。"""

    code = "LLM_AUTH"


class LLMNetworkError(LLMError):
    """网络异常。"""

    code = "LLM_NETWORK"


class UnknownProviderError(LLMError):
    """未知 provider / model。"""

    code = "LLM_UNKNOWN_PROVIDER"
