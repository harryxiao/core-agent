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

_STEP_THRESHOLD = 6
_CONCLUSION_HINTS = ("结论", "完成", "结果")
_DECISION_HINTS = ("决定", "选择", "采用")
_OPEN_HINTS = ("待", "TODO", "未决", "下一步")


class Compactor:
    """多轮上下文压实：摘要关键信息并写回记忆。"""

    def __init__(
        self, memory: MemoryStore | None = None, *, step_threshold: int = _STEP_THRESHOLD
    ) -> None:
        self._memory = memory
        self._step_threshold = step_threshold

    def should_compact(self, steps: int, token_used: int, budget: int) -> bool:
        """**本轮工具步数**或 token 达到阈值时触发压实。

        ``steps`` 是本轮内已记账的工具动作步数（`LoopContext.rounds`，每用户轮自 ``0``
        起算），**非**对话轮数（change 0182 / ADR-0173 诚实化）。触发后是否**重复**压实
        由调用方（`DefaultLoop.astream` 的本轮标记）把关 —— 本方法是**纯判据**。
        """
        return steps >= self._step_threshold or token_used >= budget

    def compact(self, history: list[dict[str, Any]]) -> Compaction:
        """从**本轮**消息（+ 工具 I/O）提取结论/决策/未决事项，标记被清理冗余。

        ``history`` 是调用点（``DefaultLoop._compact``）传入的 ``ctx.messages`` —— **仅本轮**；
        多轮历史由三层滑窗（change 0178）与记忆压实承载，本方法**不**折入（change 0192 诚实化）。
        ``from:<id>`` 出处面为**死面**：本轮消息条目无 ``id`` ⇒ ``source_ids`` 恒空、provenance
        恒不触发（仅测试以手造 ``{"id": …}`` 激活），本方法**不**扩输入面（显式不做）。
        """
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

    def persist(self, c: Compaction, *, session_id: str = "") -> None:
        """压实产物写回 MemoryStore（L2 提炼事实），丢失关键信息抛 COMPACTION_LOSSY。

        产物为 `kind="semantic"`（提炼事实，非事件），`tags` 携带贡献历史的原始 id
        （`from:<id>`）——沉淀不再是无出处的匿名条目。

        产物按**本轮会话**归属（``session_id``，缺省空串 = 未归属），条目 id 与 ``trace_id`` 均带
        会话键（缺省 ``default``，沿用 store 内既有 ``session_id or "default"`` 口径）⇒ 跨会话
        不再同名覆盖，且回滚按 ``compaction.<key>`` 细化归因、与同会话其他压实产物共组
        （change 0192，与 store 内会话摘要 / 关键事实 / 中期摘要的 trace 口径**逐字一致**）。
        """
        self._guard(c)
        if self._memory is None:
            return
        provenance = [f"from:{source_id}" for source_id in c.source_ids]
        key = session_id or "default"
        trace_id = f"compaction.{key}"
        for i, line in enumerate(c.conclusions + c.decisions):
            self._memory.write(
                "L2",
                MemoryEntry(
                    id=f"compaction.fact.{key}.{i}",
                    layer="L2",
                    content=line,
                    tags=["compaction", "fact", *provenance],
                    source="context",
                    trace_id=trace_id,
                    session_id=session_id,
                    kind="semantic",
                ),
            )
        for i, item in enumerate(c.open_items):
            self._memory.write(
                "L2",
                MemoryEntry(
                    id=f"compaction.open.{key}.{i}",
                    layer="L2",
                    content=item,
                    tags=["compaction", "open", *provenance],
                    source="context",
                    trace_id=trace_id,
                    session_id=session_id,
                    kind="semantic",
                ),
            )

    @staticmethod
    def _guard(c: Compaction) -> None:
        """压实产物无任何关键信息视为有损，拒绝写回（不替换原文）。"""
        if not c.conclusions and not c.decisions and not c.open_items:
            raise ContextError(ContextErrorCode.COMPACTION_LOSSY, "压实产物丢失关键信息")
