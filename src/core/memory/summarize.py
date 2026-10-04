"""摘要适配器（memory）。

``MemoryStore.summarizer`` 契约是 ``(list[MemoryEntry]) -> str``；LLM 侧是
「prompt → 文本」。本模块把后者桥接为前者——memory **不 import 任何 LLM / rag 抽象**
（照 ``embedding.batch_embed`` 先例、ADR-0045 同一依赖方向），prompt 文本属 memory 域，
生产侧由 L5 组合根注入模型调用。

对应接口：doc/03-interfaces/memory-interface.md §3
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from .protocol import MemoryEntry

# 摘要器契约：同一会话的 episodic 条目 → 一段可复用的提炼事实
Summarizer = Callable[[list[MemoryEntry]], str]

# 单条入 prompt 的节选上界（token 有界）
_MAX_ENTRY_CHARS = 400

_PROMPT_HEAD = (
    "你是记忆压实器。把同一会话的事件条目提炼为可复用的事实，"
    "保留结论、决策与未决事项；只输出提炼结果，不要复述过程。"
)


def build_prompt(entries: Sequence[MemoryEntry]) -> str:
    """把会话事件条目渲染为提炼 prompt（逐条节选，token 有界）。"""
    lines = [f"- {entry.content[:_MAX_ENTRY_CHARS]}" for entry in entries]
    return "\n".join([_PROMPT_HEAD, "", "会话事件：", *lines])


def summarize_with(llm: Callable[[str], str]) -> Summarizer:
    """把「prompt → 文本」的模型调用适配为 ``MemoryStore`` 的摘要契约。"""

    def _summarize(entries: list[MemoryEntry]) -> str:
        return llm(build_prompt(entries)).strip()

    return _summarize
