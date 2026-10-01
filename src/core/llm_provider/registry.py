"""Provider 注册中心（llm-provider 依赖注入）。

内核按名称 / 模型前缀解析 Provider，注册即生效；替换默认实现或接入自研
后端仅改注册处，调用方零改动。

对应接口：doc/03-interfaces/llm-provider-interface.md §4
"""

from __future__ import annotations

import threading

from .errors import UnknownProviderError
from .provider import LLMProvider
from .stdlib_provider import StdlibLLMProvider


class LLMProviderRegistry:
    """Provider 注册中心：按名称 / 模型前缀解析，未命中回落 StdlibLLMProvider。"""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._lock = threading.RLock()

    def register(self, name: str, provider: LLMProvider) -> None:
        with self._lock:
            self._providers[name] = provider

    def resolve(self, name_or_model_prefix: str) -> LLMProvider:
        with self._lock:
            if name_or_model_prefix in self._providers:
                return self._providers[name_or_model_prefix]
            # 模型前缀匹配：按最长前缀命中（如 "openai/gpt-4" → "openai"）
            for name in sorted(self._providers, key=len, reverse=True):
                if name_or_model_prefix.startswith(name):
                    return self._providers[name]
        raise UnknownProviderError(  # noqa: TRY003
            f"未注册的 provider / 模型前缀：{name_or_model_prefix}"
        )

    def default(self) -> LLMProvider:
        """未命中时回落默认实现。"""
        with self._lock:
            for name in ("default",):
                if name in self._providers:
                    return self._providers[name]
        return StdlibLLMProvider()
