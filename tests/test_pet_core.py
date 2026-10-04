"""pet-core 单元测试（生命周期 / 权威错误码 / 偏好落 L2 / 三入口 / 多宠物隔离）。"""

from __future__ import annotations

import pytest

from core.loop import LoopResult
from core.memory import MemoryEntry
from core.pet.core import (
    PetActivator,
    PetError,
    PetErrorCode,
    PetManager,
    PetSession,
    PetSessionState,
    PetTask,
    PetTaskKind,
)


class FakeLoop:
    """记录调用并返回受控结果的 fake loop。"""

    def __init__(self, reply: str = "ok", trace_id: str = "t1") -> None:
        self.reply = reply
        self.trace_id = trace_id
        self.prompts: list[str] = []

    def run(self, user_input: str) -> LoopResult:
        self.prompts.append(user_input)
        return LoopResult(reply=self.reply, trace_id=self.trace_id)


class FakeMemory:
    """记录写入并返回受控结果的 fake 记忆后端。"""

    def __init__(self) -> None:
        self.written: list[MemoryEntry] = []

    def write(self, layer: str, entry: MemoryEntry) -> str | None:
        self.written.append(entry)
        return entry.id

    def read(self, query: str, budget: int = 4096) -> list[MemoryEntry]:
        return [e for e in self.written if query in e.content]


def _task() -> PetTask:
    return PetTask(kind=PetTaskKind.INFORMATION_GATHERING, goal="收集今日新闻")


def test_start_wake_roundtrip() -> None:
    loop = FakeLoop()
    session = PetSession(loop=loop)
    session.start(_task())
    assert session.state is PetSessionState.ACTIVE
    result = session.wake()
    assert result.reply == "ok"
    assert result.trace_id == "t1"
    assert "收集今日新闻" in loop.prompts[0]


def test_duplicate_start_rejected() -> None:
    session = PetSession()
    session.start(_task())
    with pytest.raises(PetError) as exc_info:
        session.start(_task())
    assert exc_info.value.code is PetErrorCode.PET_ALREADY_ACTIVE


def test_wake_when_idle_rejected() -> None:
    with pytest.raises(PetError) as exc_info:
        PetSession().wake()
    assert exc_info.value.code is PetErrorCode.PET_NOT_ACTIVE


def test_backoff_then_wake_rejected() -> None:
    session = PetSession()
    session.start(_task())
    session.backoff(RuntimeError("boom"))
    assert session.state is PetSessionState.BACKOFF
    with pytest.raises(PetError) as exc_info:
        session.wake()
    assert exc_info.value.code is PetErrorCode.PET_BACKOFF


def test_yielding_when_busy() -> None:
    session = PetSession(busy=lambda: True)
    session.start(_task())
    with pytest.raises(PetError) as exc_info:
        session.wake()
    assert exc_info.value.code is PetErrorCode.PET_YIELDING


def test_suspend_resume_yielding() -> None:
    session = PetSession(loop=FakeLoop())
    session.start(_task())
    session.suspend()
    with pytest.raises(PetError) as exc_info:
        session.wake()
    assert exc_info.value.code is PetErrorCode.PET_YIELDING
    session.resume()
    assert session.wake().reply == "ok"


def test_terminate_clears_tasks() -> None:
    session = PetSession()
    session.start(_task())
    session.terminate()
    assert session.state is PetSessionState.TERMINATED
    with pytest.raises(PetError) as exc_info:
        session.wake()
    assert exc_info.value.code is PetErrorCode.PET_NOT_ACTIVE


def test_observe_writes_l2_preference() -> None:
    memory = FakeMemory()
    session = PetSession(memory=memory)
    session.start(_task())
    entry = session.observe("editor: vim")
    assert entry.source == "user"
    assert entry.layer == "L2"
    assert memory.written[0].source == "user"
    assert memory.written[0].layer == "L2"
    assert session.prefer("editor") == "vim"


def test_observe_without_memory_rejected() -> None:
    session = PetSession()
    session.start(_task())
    with pytest.raises(PetError) as exc_info:
        session.observe("editor: vim")
    assert exc_info.value.code is PetErrorCode.PET_PREFERENCE_WRITE_FAILED


def test_activator_three_entries() -> None:
    manager = PetManager()
    activator = PetActivator(manager=manager)
    slash = activator.activate_from_slash("pet.gather")
    cli = activator.activate_from_cli("explore", ["散步"])
    nl = activator.activate_from_nl("启动宠物收集新闻")
    assert slash.state is PetSessionState.ACTIVE
    assert cli.state is PetSessionState.ACTIVE
    assert nl.state is PetSessionState.ACTIVE
    assert len(manager.list()) == 3  # noqa: PLR2004
    assert manager.get(slash.session_id) is slash


def test_session_snapshot_restore_roundtrip() -> None:
    """snapshot→restore 保真：id / 状态 / 任务队列 / 偏好 / 唤醒计数。"""
    session = PetSession(session_id="s1", loop=FakeLoop(), memory=FakeMemory())
    session.start(_task())
    session.observe("theme:dark")
    session.wake()
    restored = PetSession.restore(session.snapshot(), loop=FakeLoop())
    assert restored.session_id == "s1"
    assert restored.state is PetSessionState.ACTIVE
    assert restored.prefer("theme") == "dark"
    assert len(restored._tasks) == 1  # noqa: SLF001 — 快照保真断言
    assert restored._wake_count == 1  # noqa: SLF001 — 快照保真断言


def test_manager_persists_registry_across_instances(tmp_path) -> None:
    """注册表落盘：注册后新 manager 加载可见；stop 后落盘同步。"""
    path = tmp_path / "pets.json"
    first = PetManager(path)
    pet = PetSession(session_id="p1", loop=FakeLoop())
    pet.start(_task())
    first.register(pet)

    reloaded = PetManager(path)
    assert [p.session_id for p in reloaded.list()] == ["p1"]
    assert reloaded.get("p1").state is PetSessionState.ACTIVE

    reloaded.stop("p1")
    assert PetManager(path).get("p1").state is PetSessionState.TERMINATED


def test_manager_restores_via_factory(tmp_path) -> None:
    """factory 注入 → 加载的记录恢复为带真依赖的活会话（identity）。"""
    path = tmp_path / "pets.json"
    PetManager(path).register(PetSession(session_id="p1", loop=FakeLoop()))

    live_loop = FakeLoop()
    restored = PetManager(path, factory=lambda rec: PetSession.restore(rec, loop=live_loop))
    assert restored.get("p1")._loop is live_loop  # noqa: SLF001 — 注入生效断言


def test_activator_injects_dependencies() -> None:
    """activator 注入的依赖透传到激活的会话（偏好可落 L2）。"""
    loop = FakeLoop()
    memory = FakeMemory()
    activator = PetActivator(PetManager(), loop=loop, memory=memory)
    session = activator.activate_from_cli("gather", ["今日新闻"])
    assert session._loop is loop  # noqa: SLF001 — 注入生效断言
    assert session._memory is memory  # noqa: SLF001 — 注入生效断言
    session.observe("theme:dark")
    assert memory.written, "偏好应经注入的记忆后端落 L2"


def test_manager_multi_pet_isolation() -> None:
    manager = PetManager()
    a = PetSession(loop=FakeLoop())
    b = PetSession(loop=FakeLoop())
    manager.register(a)
    manager.register(b)
    a.start(_task())
    b.start(PetTask(kind=PetTaskKind.IDLE_EXPLORATION, goal="闲逛"))
    a.backoff(RuntimeError("a 故障"))
    # A 退避不影响 B 唤醒
    assert b.wake().reply == "ok"
    assert a.state is PetSessionState.BACKOFF
    assert b.state is PetSessionState.ACTIVE
