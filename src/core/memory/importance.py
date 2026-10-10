"""重要度评分适配器（memory）。

``MemoryStore.importance_scorer`` 契约是 ``Callable[[MemoryEntry], float]``（返回 [0,1]）；
LLM 侧是「prompt → 文本」。本模块把后者桥接为前者 —— memory **不 import 任何 LLM / rag 抽象**
（照 ``summarize.summarize_with`` / ``extract.extract_with`` 先例、ADR-0045 同一依赖方向），
prompt 文本属 memory 域，生产侧由 L5 组合根注入模型调用。

**失败方向恒为放行**：解析不出数值即抛（由闸门既有异常路径降级放行）；界外值**原样返回**
（由闸门既有界外路径降级放行）。工厂**不**兜底、**不** clamp —— 把「模型没给分」静默成 0 分
会让条目被误杀（P5 记忆先行）。

对应接口：doc/03-interfaces/memory-interface.md §3
规格：doc/openspec/specs/memory/spec.md「写入侧重要度闸门」（change 0181 / ADR-0172）
"""

from __future__ import annotations

import re
from collections.abc import Callable

from .protocol import MemoryEntry
from .store import ImportanceScorer

# 单条入 prompt 的正文节选上界（token 有界；与 `summarize._MAX_ENTRY_CHARS` 同口径）
_MAX_ENTRY_CHARS = 400

_PROMPT_HEAD = (
    "你是记忆重要度评分器。判断这条记忆对后续任务的价值，只输出 0 到 1 之间的一个数值"
    "（1 = 高度可复用，0 = 无价值），不要解释。"
)

# 模型输出中的**首个**数值（散文包裹时取首个；不锁定小数位，兼容 `1` 与 `0.8`）
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def build_score_prompt(entry: MemoryEntry) -> str:
    """把一条待写入条目渲染为评分 prompt（正文节选，token 有界）。"""
    return "\n".join(
        [
            _PROMPT_HEAD,
            "",
            f"层：{entry.layer}",
            f"来源：{entry.source}",
            f"内容：{entry.content[:_MAX_ENTRY_CHARS]}",
        ]
    )


def score_with(llm: Callable[[str], str]) -> ImportanceScorer:
    """把「prompt → 文本」的模型调用适配为 ``MemoryStore`` 的评分契约。

    无可用数值 ⇒ 抛 ``ValueError``（消息**只含输出长度**，绝不回显正文 —— 正文可能含明文密钥）。
    """

    def _score(entry: MemoryEntry) -> float:
        text = llm(build_score_prompt(entry))
        found = _NUMBER.search(text)
        if found is None:
            raise ValueError(f"importance score unparseable ({len(text)} chars)")  # noqa: TRY003
        return float(found.group())

    return _score
