"""上下文压实（Compactor）。

多轮关键信息摘要沉淀，写回 MemoryStore，避免重复传递冗余内容；压实产物
校验关键信息不丢失，丢失则抛 COMPACTION_LOSSY 且不替换原文。本压实器是
**启发式降级路径**（关键词识别结论/决策/未决事项）：LLM 提炼统一由记忆压实通道
（``memory.summarize``）承担，此处不新增模型调用点。

对应接口：doc/03-interfaces/context-interface.md §4
"""

from __future__ import annotations

from typing import Any

from core.memory import MemoryEntry, MemoryStore

from .errors import ContextError, ContextErrorCode
from .models import Compaction

_ROUND_THRESHOLD = 10
_CONCLUSION_HINTS = ("结论", "完成", "结果")
_DECISION_HINTS = ("决定", "选择", "采用")
_OPEN_HINTS = ("待", "TODO", "未决", "下一步")


class Compactor:
    """多轮上下文压实：摘要关键信息并写回记忆。"""

    def __init__(
        self, memory: MemoryStore | None = None, *, round_threshold: int = _ROUND_THRESHOLD
    ) -> None:
        self._memory = memory
        self._round_threshold = round_threshold

    def should_compact(self, rounds: int, token_used: int, budget: int) -> bool:
        """轮数或 token 达到阈值时触发压实。"""
        return rounds >= self._round_threshold or token_used >= budget

    def compact(self, history: list[dict[str, Any]]) -> Compaction:
        """从多轮历史提取结论/决策/未决事项，标记被清理冗余。"""
        conclusions: list[str] = []
        decisions: list[str] = []
        open_items: list[str] = []
        dropped: list[str] = []
        source_ids: list[str] = []
        for entry in history:
            content = str(entry.get("content", ""))
            entry_id = str(entry.get("id", ""))
            if not content:
                continue
            contributed = False
            if any(hint in content for hint in _CONCLUSION_HINTS):
                conclusions.append(content)
                contributed = True
            if any(hint in content for hint in _DECISION_HINTS):
                decisions.append(content)
                contributed = True
            if any(hint in content for hint in _OPEN_HINTS):
                open_items.append(content)
                contributed = True
            if contributed and entry_id:
                source_ids.append(entry_id)
            if entry.get("redundant") and entry_id:
                dropped.append(entry_id)
        return Compaction(
            conclusions=conclusions,
            decisions=decisions,
            open_items=open_items,
            dropped=dropped,
            source_ids=source_ids,
        )

    def persist(self, c: Compaction) -> None:
        """压实产物写回 MemoryStore（L2 提炼事实），丢失关键信息抛 COMPACTION_LOSSY。

        产物为 `kind="semantic"`（提炼事实，非事件），`tags` 携带贡献历史的原始 id
        （`from:<id>`）——沉淀不再是无出处的匿名条目。
        """
        self._guard(c)
        if self._memory is None:
            return
        provenance = [f"from:{source_id}" for source_id in c.source_ids]
        for i, line in enumerate(c.conclusions + c.decisions):
            self._memory.write(
                "L2",
                MemoryEntry(
                    id=f"compaction.fact.{i}",
                    layer="L2",
                    content=line,
                    tags=["compaction", "fact", *provenance],
                    source="context",
                    trace_id="compaction",
                    kind="semantic",
                ),
            )
        for i, item in enumerate(c.open_items):
            self._memory.write(
                "L2",
                MemoryEntry(
                    id=f"compaction.open.{i}",
                    layer="L2",
                    content=item,
                    tags=["compaction", "open", *provenance],
                    source="context",
                    trace_id="compaction",
                    kind="semantic",
                ),
            )

    @staticmethod
    def _guard(c: Compaction) -> None:
        """压实产物无任何关键信息视为有损，拒绝写回（不替换原文）。"""
        if not c.conclusions and not c.decisions and not c.open_items:
            raise ContextError(ContextErrorCode.COMPACTION_LOSSY, "压实产物丢失关键信息")
