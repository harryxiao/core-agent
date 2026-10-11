"""情景归纳适配器（memory）。

``MemoryStore`` 的归纳契约是 ``(list[MemoryEntry]) -> str``；LLM 侧是「prompt → 文本」。
本模块把后者桥接为前者 —— memory **不 import 任何 LLM / rag 抽象**（照
``summarize.summarize_with`` / ``extract.extract_with`` 先例、ADR-0045 同一依赖方向），
prompt 文本属 memory 域，生产侧由 L5 组合根注入模型调用。

**与摘要器的区别**（二者**刻意不共用** prompt 文本）：摘要器把「既有摘要」当**滚动合并**输入
并**迁移**来源条目；归纳器只看本批事件、**不迁移**任何条目，产出面向会话的**结论快照**
（目标 / 经过 / 结果 / 教训）。共用文本会使两路互相污染（见 change 0218 / ADR-0208）。

**密钥红线**：本模块不做脱敏 —— 脱敏由 store 侧在**落库前无条件**执行（`redact_secrets`，
注入的归纳器**不构成信任边界**），方向恒 over-redact。

对应接口：doc/03-interfaces/memory-interface.md §3
规格：doc/openspec/specs/memory/spec.md「情景归纳（episodic consolidation）」
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from .protocol import MemoryEntry

# 归纳器契约：同一批被压实的会话事件 → 一段情景归纳文本（目标 / 经过 / 结果 / 教训）
EpisodicExtractor = Callable[[list[MemoryEntry]], str]

# 单条入 prompt 的事件节选上界（token 有界；与 `summarize._MAX_ENTRY_CHARS` 同口径）
_MAX_ENTRY_CHARS = 400

# 落库长度上界（**独立常量**：与 `summarize.MAX_SUMMARY_CHARS` 数值同刻度，但二者是独立旋钮，
# 改一处不应静默改另一处）。
MAX_EPISODIC_CHARS = 2000

_PROMPT_HEAD = (
    "你是情景归纳器。把下面这段会话事件归纳为一段**结论快照**，四段结构依次写："
    "目标（这段会话要做什么）、经过（实际怎么做的）、结果（最终达成了什么）、"
    "教训（下次同类任务该注意什么 —— 须写成可复用的判据，而非「下次小心」这类空话）。"
    "只输出归纳本身，不要复述过程、不要罗列原始事件。"
)


def build_episodic_prompt(entries: Sequence[MemoryEntry]) -> str:
    """把会话事件条目渲染为归纳 prompt（逐条节选，token 有界）。"""
    heads = [_PROMPT_HEAD, "", "会话事件："]
    lines = [f"- {entry.content[:_MAX_ENTRY_CHARS]}" for entry in entries]
    return "\n".join([*heads, *lines])


def consolidate_with(llm: Callable[[str], str]) -> EpisodicExtractor:
    """把「prompt → 文本」的模型调用适配为 ``MemoryStore`` 的归纳契约。"""

    def _consolidate(entries: list[MemoryEntry]) -> str:
        return llm(build_episodic_prompt(entries)).strip()

    return _consolidate
