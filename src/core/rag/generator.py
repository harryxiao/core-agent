"""生成融合（rag）。

检索片段作为上下文注入生成链路：按预算裁剪后注入提示词 → llm-provider 生成；
``hits`` 为空时降级为纯 LLM 生成（不阻断流程）。

对应接口：doc/03-interfaces/rag-interface.md §5
"""

from __future__ import annotations

from core.llm_provider import LLMProvider, LLMRequest, Message

from .models import SearchHit


class RagGenerator:
    """检索增强生成：片段上下文注入 → 模型生成。"""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        model: str = "default",
        max_context_chars: int = 2048,
    ) -> None:
        self._provider = provider
        self._model = model
        self._max_context_chars = max_context_chars

    def generate(self, query: str, hits: list[SearchHit]) -> str:
        """检索片段按预算裁剪后注入提示词 → llm-provider 生成；空 hits 降级纯 LLM。"""
        context = "\n\n".join(f"[片段{i}] {hit.chunk.text}" for i, hit in enumerate(hits, start=1))
        context = context[: self._max_context_chars]
        prompt = f"参考以下检索片段回答：\n\n{context}\n\n问题：{query}" if hits else query
        response = self._provider.completion(
            LLMRequest(messages=[Message(role="user", content=prompt)], model=self._model)
        )
        return response.content
