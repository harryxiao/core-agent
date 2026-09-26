"""统一请求 / 响应模型（llm-provider）。

内核只面向这些数据模型，不感知底层供应商协议差异。``tools`` 字段以
``list[Any]`` 承载（避免反向依赖 tool-use 的 ``ToolDef``），实现层按需解析。

对应接口：doc/03-interfaces/llm-provider-interface.md §2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class Message:
    """一条对话消息。"""

    role: Literal["system", "user", "assistant", "tool"]
    content: str


@dataclass
class LLMRequest:
    """统一补全请求。"""

    messages: list[Message]
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None
    tools: list[Any] | None = None


@dataclass
class TokenUsage:
    """令牌用量统计。"""

    prompt_tokens: int
    completion_tokens: int


@dataclass
class LLMResponse:
    """统一补全响应（含审计标注）。"""

    content: str
    usage: TokenUsage
    finish_reason: str
    provider: str  # 审计标注：实际响应的 provider
    model: str  # 审计标注：实际使用的 model


@dataclass
class Embedding:
    """向量化结果。"""

    vector: list[float]


@dataclass
class LLMChunk:
    """流式响应增量块。"""

    content: str
