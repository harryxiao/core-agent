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
    # 推理档位（OpenAI 风格 low/medium/high）：None 不下发（端点不支持该字段时零影响）
    reasoning_effort: str | None = None


@dataclass
class TokenUsage:
    """令牌用量统计。"""

    prompt_tokens: int
    completion_tokens: int


@dataclass
class ToolCall:
    """原生 function call（OpenAI 兼容 tool_calls 的统一形状）。

    流式响应中为增量片段：``index`` 标识归属，``tool_id``/``call_id`` 仅首片携带，
    ``arguments`` 为 JSON 字符串的增量拼接段，由消费方按 index 累积。
    """

    tool_id: str  # function.name
    arguments: str  # 参数 JSON 字符串
    call_id: str | None = None
    index: int = 0  # 流式片段归属索引


@dataclass
class LLMResponse:
    """统一补全响应（含审计标注）。"""

    content: str
    usage: TokenUsage
    finish_reason: str
    provider: str  # 审计标注：实际响应的 provider
    model: str  # 审计标注：实际使用的 model
    tool_calls: list[ToolCall] | None = None  # 原生 function call（缺失走 content 协议）


@dataclass
class Embedding:
    """向量化结果。"""

    vector: list[float]


@dataclass
class LLMChunk:
    """流式响应增量块。"""

    content: str
    tool_calls: list[ToolCall] | None = None  # delta.tool_calls 增量片段
