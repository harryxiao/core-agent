"""pet-core 单元测试（生命周期 / 权威错误码 / 偏好落 L2 / 三入口 / 多宠物隔离）。"""

from __future__ import annotations

import pytest

from core.loop import LoopResult
from core.memory import MemoryEntry
from core.pet_core import (
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
