"""beast-mode 单元测试（二十神兽 / 神通注册 / 四态生命周期 / 多兽并发 / 三入口）。"""

from __future__ import annotations

import asyncio

import pytest

from core.beast import (
    BeastActivator,
    BeastError,
    BeastErrorCode,
    BeastManager,
    BeastRegistry,
    BeastSession,
    BeastSessionState,
    build_innate_skills,
    register_innate_skills,
)
from core.loop import LoopResult
from core.memory import MemoryEntry
from core.orchestration import AgentProfile, OrchestrationError, OrchestrationErrorCode
from core.skills import SkillLibrary


class FakeMemory:
    """记录写入并返回受控结果的 fake 记忆后端。"""

    def __init__(self) -> None:
        self.written: list[MemoryEntry] = []

    def write(self, layer: str, entry: MemoryEntry) -> str | None:
        self.written.append(entry)
        return entry.id

    def read(self, query: str, budget: int = 4096) -> list[MemoryEntry]:
        return [e for e in self.written if query in e.content]


class FakeRouter:
    """记录 register/handoff 并返回受控 LoopResult 的 fake 路由器。"""

    def __init__(
        self,
        reply: str = "ok",
        trace_id: str = "t1",
        failed: bool = False,
        error: Exception | None = None,
    ) -> None:
        self.reply = reply
        self.trace_id = trace_id
        self.failed = failed
        self.error = error
        self.profiles: list[AgentProfile] = []
        self.handoffs: list[tuple[str, object]] = []

    def register(self, profile: AgentProfile) -> None:
        self.profiles.append(profile)

    async def handoff(self, target: str, handoff: object) -> LoopResult:
        self.handoffs.append((target, handoff))
        if self.error is not None:
            raise self.error
        return LoopResult(reply=self.reply, trace_id=self.trace_id, failed=self.failed)


def _session() -> BeastSession:
    return BeastSession(BeastRegistry().lookup("beast.qinglong") or BeastRegistry().all()[0])


def test_registry_twenty_beasts_read_only() -> None:
    registry = BeastRegistry()
    assert len(registry.all()) == 20  # noqa: PLR2004
    qinglong = registry.lookup("beast.qinglong")
    assert qinglong is not None
    assert qinglong.title == "青龙"
    assert qinglong.innate_skill == "beast.qinglong.blueprint"
    # 别名解析：agent_id / 称号 / 拼音 三等价
    assert registry.resolve("青龙") is qinglong
    assert registry.resolve("qinglong") is qinglong
    assert registry.resolve("beast.qinglong") is qinglong
    assert registry.resolve("不存在的兽") is None


def test_register_innate_skills() -> None:
    registry = BeastRegistry()
    skills = build_innate_skills(registry)
    assert len(skills) == 20  # noqa: PLR2004
    assert all(s.skill_id.startswith("beast.") for s in skills)
    library = SkillLibrary()
    assert register_innate_skills(library, registry) == 20  # noqa: PLR2004
    assert library.lookup("beast.qinglong.blueprint").description.startswith("青龙")


def test_summon_recall_roundtrip() -> None:
    session = _session()
    session.summon()
    assert session.state is BeastSessionState.ACTIVE
    session.recall()
    assert session.state is BeastSessionState.RECALLED
    session.summon()  # 召回后可再次召唤
    assert session.state is BeastSessionState.ACTIVE


def test_duplicate_summon_rejected() -> None:
    session = _session()
    session.summon()
    with pytest.raises(BeastError) as exc_info:
        session.summon()
    assert exc_info.value.code is BeastErrorCode.BEAST_ALREADY_MANIFEST


def test_activate_when_not_manifest_rejected() -> None:
    with pytest.raises(BeastError) as exc_info:
        _session().activate()
    assert exc_info.value.code is BeastErrorCode.BEAST_NOT_MANIFEST


def test_recall_when_dormant_rejected() -> None:
    with pytest.raises(BeastError) as exc_info:
        _session().recall()
    assert exc_info.value.code is BeastErrorCode.BEAST_NOT_MANIFEST


def test_remember_writes_beast_namespace() -> None:
    memory = FakeMemory()
    session = BeastSession(
        BeastRegistry().lookup("beast.qinglong") or BeastRegistry().all()[0],
        memory=memory,
    )
    session.summon()
    entry = session.remember("架构方案已生成")
    assert entry.source == "beast.qinglong"
    assert entry.layer == "L2"
    assert memory.written[0].source == "beast.qinglong"
    assert memory.written[0].tags == ["beast"]


def test_remember_without_memory_rejected() -> None:
    session = _session()
    with pytest.raises(BeastError) as exc_info:
        session.remember("x")
    assert exc_info.value.code is BeastErrorCode.BEAST_MEMORY_WRITE_FAILED


def test_manager_multi_beast_parallel() -> None:
    manager = BeastManager()

    async def _run() -> tuple[BeastSession, BeastSession]:
        a = await manager.summon("beast.qinglong", "架构系统")
        b = await manager.summon("beast.baihu", "剖析瓶颈")
        return a, b

    a, b = asyncio.run(_run())
    assert a.state is BeastSessionState.ACTIVE
    assert b.state is BeastSessionState.ACTIVE
    assert len(manager.active()) == 2  # noqa: PLR2004
    assert manager.get("beast.qinglong") is a


def test_manager_same_beast_duplicate_rejected() -> None:
    manager = BeastManager()

    async def _run() -> None:
        await manager.summon("beast.qinglong")
        await manager.summon("beast.qinglong")

    with pytest.raises(BeastError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code is BeastErrorCode.BEAST_ALREADY_MANIFEST


def test_manager_unknown_beast_no_agent_match() -> None:
    async def _run() -> None:
        await BeastManager().summon("beast.nonexistent")

    with pytest.raises(OrchestrationError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code is OrchestrationErrorCode.NO_AGENT_MATCH


def test_manager_summon_is_handoff() -> None:
    router = FakeRouter()
    manager = BeastManager(router=router)
    session = asyncio.run(manager.summon("青龙", "架构一个订单系统"))
    assert len(router.profiles) == 1
    assert router.profiles[0].agent_id == "beast.qinglong"
    assert router.handoffs[0][0] == "beast.qinglong"
    assert session.last_trace_id == "t1"
    assert session.last_result is not None
    assert session.last_result.trace_id == "t1"
    assert session.last_result.failed is False
    assert session.state is BeastSessionState.RECALLED  # 任务完成 → 自动回归


def test_manager_summon_failed_still_recalled() -> None:
    """无论任务成败，handoff 完成即自动回归，failed 如实记录于 last_result。"""
    router = FakeRouter(failed=True)
    manager = BeastManager(router=router)
    session = asyncio.run(manager.summon("beast.qinglong"))
    assert session.last_result is not None
    assert session.last_result.failed is True
    assert session.state is BeastSessionState.RECALLED  # 失败也自动回归


def test_manager_summon_recalls_on_handoff_error() -> None:
    """交接抛错（含超时）也回归 RECALLED，不滞留 ACTIVE（change 0247）。"""
    router = FakeRouter(error=OrchestrationError(OrchestrationErrorCode.NO_AGENT_MATCH, "boom"))
    manager = BeastManager(router=router)
    with pytest.raises(OrchestrationError):
        asyncio.run(manager.summon("beast.qinglong"))
    assert manager.active() == []
    session = manager.get("beast.qinglong")
    assert session is not None
    assert session.state is BeastSessionState.RECALLED


def test_manager_recall_resets_target_only() -> None:
    manager = BeastManager()

    async def _run() -> tuple[BeastSession, BeastSession]:
        a = await manager.summon("beast.qinglong")
        b = await manager.summon("beast.baihu")
        return a, b

    a, b = asyncio.run(_run())
    manager.recall("beast.qinglong")
    assert a.state is BeastSessionState.RECALLED
    assert b.state is BeastSessionState.ACTIVE


def test_activator_three_entries() -> None:
    manager = BeastManager()
    activator = BeastActivator(manager=manager)

    async def _run() -> tuple[BeastSession, BeastSession, BeastSession]:
        slash = await activator.activate_from_slash("青龙", "架构系统")
        cli = await activator.activate_from_cli("beast.baihu", ["剖析", "瓶颈"])
        nl = await activator.activate_from_nl("召唤 玄武 审计安全")
        return slash, cli, nl

    slash, cli, nl = asyncio.run(_run())
    assert slash.state is BeastSessionState.ACTIVE
    assert cli.state is BeastSessionState.ACTIVE
    assert nl.state is BeastSessionState.ACTIVE
    assert len(manager.all()) == 3  # noqa: PLR2004
    assert manager.get("beast.xuanwu") is nl


def test_activator_recall_entries() -> None:
    manager = BeastManager()
    activator = BeastActivator(manager=manager)

    async def _summon() -> None:
        await activator.activate_from_slash("青龙")
        await activator.activate_from_cli("beast.baihu", ["剖析"])
        await activator.activate_from_nl("召唤 玄武 审计安全")

    asyncio.run(_summon())
    # 三入口复位：slash / CLI / NL 均落到 manager.recall
    assert activator.recall_from_slash("青龙").state is BeastSessionState.RECALLED
    assert activator.recall_from_cli("beast.baihu").state is BeastSessionState.RECALLED
    assert activator.recall_from_nl("召回 玄武").state is BeastSessionState.RECALLED
