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

# 既有摘要的节选上界——独立于单条事件上界：摘要若同受 400 字截断，「滚动合并」即失效
_MAX_SUMMARY_CHARS = 2000

# 既有摘要条目的判据（store 落库时 `tags` 含 `summary`，见 `_commit_summary`）
_SUMMARY_TAG = "summary"

_PROMPT_HEAD = (
    "你是记忆压实器。把新的会话事件合并进既有摘要，保留结论、决策与未决事项；"
    "既有摘要为空则据事件首次提炼。只输出更新后的摘要，不要复述过程。"
)


def build_prompt(entries: Sequence[MemoryEntry]) -> str:
    """把会话事件条目渲染为提炼 prompt（逐条节选，token 有界）。

    既有摘要条目（``tags`` 含 ``summary``）SHALL 渲染为显式「现有摘要」槽位——摘要为
    **滚动合并**（既有结论 + 新增事件 → 更新后的摘要），既有结论不被静默丢弃。
    """
    prior = next((entry for entry in entries if _SUMMARY_TAG in entry.tags), None)
    heads = [_PROMPT_HEAD, ""]
    if prior is not None:
        heads += ["现有摘要：", prior.content[:_MAX_SUMMARY_CHARS], ""]
    heads.append("会话事件：")
    lines = [f"- {entry.content[:_MAX_ENTRY_CHARS]}" for entry in entries if entry is not prior]
    return "\n".join([*heads, *lines])


def summarize_with(llm: Callable[[str], str]) -> Summarizer:
    """把「prompt → 文本」的模型调用适配为 ``MemoryStore`` 的摘要契约。"""

    def _summarize(entries: list[MemoryEntry]) -> str:
        return llm(build_prompt(entries)).strip()

    return _summarize
