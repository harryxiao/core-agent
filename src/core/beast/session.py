"""神兽会话生命周期（beast-mode，会话层）。

BeastSession 是单只神兽的会话句柄：DORMANT → MANIFEST → ACTIVE → RECALLED
四态状态机收口；召唤显形/执行/召回/复位全生命周期；独立记忆命名空间以
``MemoryEntry.source = beast.<agent_id>`` 落 L2 facts 层，与主 Agent
（``source=loop``）隔离。独立 ``LoopPlugin`` 实例（独立上下文 + 独立记忆）。

对应规格：doc/openspec/specs/beast-mode/spec.md（Beast Session Lifecycle）
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from core.loop import DefaultLoop, LoopPlugin, LoopResult
from core.memory import MemoryEntry, MemoryStore

from .errors import BeastError, BeastErrorCode
from .models import Beast, BeastSessionState


class BeastSession:
    """单只神兽会话：前台重大任务的生命周期与独立记忆。"""

    def __init__(
        self,
        beast: Beast,
        *,
        loop: LoopPlugin | None = None,
        memory: MemoryStore | None = None,
    ) -> None:
        self.beast = beast
        self.state = BeastSessionState.DORMANT
        self.loop: LoopPlugin = loop if loop is not None else cast(LoopPlugin, DefaultLoop())
        self._memory = memory
        self.last_trace_id = ""
        self.last_result: LoopResult | None = None

    # ---- 生命周期（四态状态机） ----

    def manifest(self) -> None:
        """显形：DORMANT / RECALLED → MANIFEST；已在岗重复显形被拒。"""
        if self.state in (BeastSessionState.MANIFEST, BeastSessionState.ACTIVE):
            raise BeastError(
                BeastErrorCode.BEAST_ALREADY_MANIFEST,
                f"神兽 {self.beast.agent_id} 已在岗，重复召唤被拒",
            )
        self.state = BeastSessionState.MANIFEST

    def activate(self) -> None:
        """开始执行：MANIFEST → ACTIVE；未显形无法激活。"""
        if self.state is not BeastSessionState.MANIFEST:
            raise BeastError(
                BeastErrorCode.BEAST_NOT_MANIFEST,
                f"神兽 {self.beast.agent_id} 未显形，无法激活",
            )
        self.state = BeastSessionState.ACTIVE

    def summon(self) -> None:
        """召唤 = 显形 + 激活：DORMANT / RECALLED → ACTIVE。"""
        self.manifest()
        self.activate()

    def recall(self) -> None:
        """召回/复位：MANIFEST / ACTIVE → RECALLED；无在岗兽召回无效。"""
        if self.state not in (BeastSessionState.MANIFEST, BeastSessionState.ACTIVE):
            raise BeastError(
                BeastErrorCode.BEAST_NOT_MANIFEST,
                f"神兽 {self.beast.agent_id} 无在岗，召回无效",
            )
        self.state = BeastSessionState.RECALLED

    # ---- 独立记忆 ----

    def remember(self, content: str, trace_id: str = "") -> MemoryEntry:
        """神兽执行产物以 ``source=beast.<agent_id>`` 落 L2，与主记忆隔离。"""
        if self._memory is None:
            raise BeastError(
                BeastErrorCode.BEAST_MEMORY_WRITE_FAILED,
                "记忆后端未接，神兽记忆无法落 L2",
            )
        entry = MemoryEntry(
            id=uuid.uuid4().hex,
            layer="L2",
            content=content,
            tags=["beast"],
            source=self.beast.agent_id,
            trace_id=trace_id or self.last_trace_id or uuid.uuid4().hex,
        )
        if self._memory.write("L2", entry) is None:
            raise BeastError(
                BeastErrorCode.BEAST_MEMORY_WRITE_FAILED,
                "神兽记忆写入 L2 facts 层失败",
            )
        return entry

    # ---- 结果可见性（change 0113 / E46） ----

    def result_summary(self) -> dict[str, Any]:
        """最近一次交接结果的**只读**摘要（神兽 id / 是否有结果 / 结果正文 / 成败）。

        数据源为会话持有的 ``last_result``（`handoff` 返回值）——**只读、不落库、不写 L2**。
        结果可见性不走主 loop 检索：神兽记忆分区封存（`source=beast.*` 不被主 loop read 命中）
        语义**不受影响**（beast-mode spec「Task Result Visibility」）。
        """
        result = self.last_result
        return {
            "agent_id": self.beast.agent_id,
            "has_result": result is not None,
            "reply": result.reply if result is not None else None,
            "failed": result.failed if result is not None else None,
        }
