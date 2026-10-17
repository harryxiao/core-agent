"""多神兽管理（beast-mode，会话层）。

维护 ``dict[agent_id, BeastSession]`` 多实例：可同时显形多兽并行执行
（兽间并行、互不阻塞）；同兽重复召唤拒绝（兽内串行、无同兽双实例）。
召唤 = 复用编排层 ``MultiAgentRouter.handoff`` 交接语义（神兽即内置
``AgentProfile``），不另造第二真源。会话按 ``loop_factory`` 惰性装配独立 loop
（按兽作用域路由神通）并注入共享 ``MemoryStore``——缺省不注入（库层零行为变化）。

对应规格：doc/openspec/specs/beast-mode/spec.md（Beast Session Lifecycle / Summon via Handoff）
"""

from __future__ import annotations

from collections.abc import Callable

from core.loop import LoopPlugin
from core.memory import MemoryStore
from core.orchestration import (
    AgentProfile,
    MultiAgentRouter,
    OrchestrationError,
    OrchestrationErrorCode,
    TaskHandoff,
)

from .errors import BeastError, BeastErrorCode
from .models import Beast, BeastSessionState
from .registry import BeastRegistry
from .session import BeastSession


class BeastManager:
    """多神兽注册表：兽间并行、兽内串行的召唤/召回编排。"""

    def __init__(
        self,
        *,
        registry: BeastRegistry | None = None,
        router: MultiAgentRouter | None = None,
        loop_factory: Callable[[Beast], LoopPlugin] | None = None,
        memory: MemoryStore | None = None,
    ) -> None:
        self._registry = registry if registry is not None else BeastRegistry()
        self._router = router
        self._loop_factory = loop_factory
        self._memory = memory
        self._sessions: dict[str, BeastSession] = {}

    async def summon(self, agent_id: str, task: str = "") -> BeastSession:
        """召唤神兽：解析 → 建会话 → 显形激活 → 异步 handoff 交接 → 自动回归。"""
        beast = self._registry.resolve(agent_id)
        if beast is None:
            raise OrchestrationError(
                OrchestrationErrorCode.NO_AGENT_MATCH, f"无匹配神兽: {agent_id}"
            )
        session = self._sessions.get(beast.agent_id)
        if session is None:
            # 按兽装配独立 loop（域内技能路由作用域）+ 注入共享记忆（命名空间隔离靠 source 标签）
            loop = self._loop_factory(beast) if self._loop_factory is not None else None
            session = BeastSession(beast, loop=loop, memory=self._memory)
            self._sessions[beast.agent_id] = session
        session.summon()  # 已在岗（MANIFEST/ACTIVE）→ BEAST_ALREADY_MANIFEST
        if self._router is not None:
            profile = AgentProfile(
                agent_id=beast.agent_id,
                capabilities=list(beast.capabilities),
                loop=session.loop,
            )
            self._router.register(profile)
            try:
                result = await self._router.handoff(
                    beast.agent_id,
                    TaskHandoff(task=task or beast.domain, session_id=beast.agent_id),
                )
            finally:
                # 任务收口（成功 / 失败 / 超时 / 异常）都必须回归 RECALLED，不滞留 ACTIVE。
                session.recall()
            session.last_result = result
            session.last_trace_id = result.trace_id
        return session

    def recall(self, agent_id: str) -> BeastSession:
        """召回指定神兽：MANIFEST / ACTIVE → RECALLED，他兽不受影响。"""
        beast = self._registry.resolve(agent_id)
        if beast is None:
            raise OrchestrationError(
                OrchestrationErrorCode.NO_AGENT_MATCH, f"无匹配神兽: {agent_id}"
            )
        session = self._sessions.get(beast.agent_id)
        if session is None:
            raise BeastError(
                BeastErrorCode.BEAST_NOT_MANIFEST,
                f"神兽 {beast.agent_id} 无在岗，召回无效",
            )
        session.recall()
        return session

    def get(self, agent_id: str) -> BeastSession | None:
        """按 agent_id 取在册会话。"""
        return self._sessions.get(agent_id)

    def active(self) -> list[BeastSession]:
        """当前在岗（MANIFEST / ACTIVE）的神兽会话。"""
        return [
            s
            for s in self._sessions.values()
            if s.state in (BeastSessionState.MANIFEST, BeastSessionState.ACTIVE)
        ]

    def all(self) -> list[BeastSession]:
        """全部在册会话。"""
        return list(self._sessions.values())
