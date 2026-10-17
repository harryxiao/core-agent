"""多 Agent 协同路由（orchestration）。

按子 Agent 能力标签匹配任务并交接（handoff）；无匹配 Agent 时报
``NO_AGENT_MATCH``。匹配为关键词式能力打分（离线简单判定），语义匹配
留待进化引擎 / 模型路由（Phase 5）。

交接执行统一委托 ``handoff`` 模块（beast / pet / 调度器同一实现；
change 0247 / ADR-0235）。

对应接口：doc/03-interfaces/orchestration-interface.md §3
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from core.loop import LoopEvent, LoopPlugin, LoopResult

from .errors import OrchestrationError, OrchestrationErrorCode
from .handoff import run_handoff, stream_handoff
from .models import AgentProfile, TaskHandoff


class MultiAgentRouter:
    """多 Agent 路由器：能力匹配 + 显式交接。"""

    def __init__(
        self,
        agents: list[AgentProfile] | None = None,
        *,
        fallback: AgentProfile | None = None,
    ) -> None:
        self._agents: dict[str, AgentProfile] = {a.agent_id: a for a in (agents or [])}
        self._fallback = fallback

    def register(self, profile: AgentProfile) -> None:
        """登记子 Agent 画像（按 id 覆盖）。"""
        self._agents[profile.agent_id] = profile

    def match(self, task: str) -> AgentProfile:
        """按能力标签打分匹配最佳 Agent；无命中回落 fallback，均无则抛 NO_AGENT_MATCH。"""
        best: AgentProfile | None = None
        best_score = 0
        lowered = task.lower()
        for profile in self._agents.values():
            score = sum(1 for cap in profile.capabilities if cap.lower() in lowered)
            if score > best_score:
                best, best_score = profile, score
        if best is not None:
            return best
        if self._fallback is not None:
            return self._fallback
        raise OrchestrationError(OrchestrationErrorCode.NO_AGENT_MATCH, f"无匹配 Agent: {task}")

    async def handoff(self, target: str, handoff: TaskHandoff) -> LoopResult:
        """显式交接任务给指定 Agent，异步执行并返回完整 LoopResult；无匹配抛错。"""
        loop = self._resolve(target)
        return await run_handoff(loop, handoff, deadline=handoff.deadline)

    def handoff_stream(self, target: str, handoff: TaskHandoff) -> AsyncIterator[LoopEvent]:
        """流式交接：先解析目标（同步 fail-fast），再按 deadline 产出子 Agent 事件流。"""
        loop = self._resolve(target)
        return stream_handoff(loop, handoff, deadline=handoff.deadline)

    def _resolve(self, target: str) -> LoopPlugin:
        """按 id 解析执行单元；包含未登记但被 ``match`` 命中的 fallback 画像。"""
        profile = self._agents.get(target)
        if profile is None and self._fallback is not None and self._fallback.agent_id == target:
            profile = self._fallback
        if profile is None or profile.loop is None:
            raise OrchestrationError(
                OrchestrationErrorCode.NO_AGENT_MATCH, f"无匹配 Agent: {target}"
            )
        return profile.loop
