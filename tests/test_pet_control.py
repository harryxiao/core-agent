"""pet 控制面单元测试（change 0088 / 用户诉求①）。

控制面 = verb → 会话操作 + 会话寻址，由单一 `PetControl` 门面收口（CLI 与 UIAPILayer 复用）。
核心契约：单宠物默认寻址 / 多宠物须显式（不猜测）/ 未知会话 `PET_NOT_FOUND`；
`status` 结构化且**不外泄**主人偏好与任务正文。
"""

from __future__ import annotations

import pytest

from core.loop import LoopResult
from core.memory import MemoryEntry
from core.pet.core import (
    PetControl,
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

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def run(self, user_input: str, *, session_id: str = "") -> LoopResult:
        self.prompts.append(user_input)
        return LoopResult(reply="ok", trace_id="t1")


class FakeMemory:
    """记录写入的 fake 记忆后端（供偏好落 L2）。"""

    def __init__(self) -> None:
        self.written: list[MemoryEntry] = []

    def write(self, layer: str, entry: MemoryEntry) -> str | None:
        self.written.append(entry)
        return entry.id

    def read(self, query: str, budget: int = 4096) -> list[MemoryEntry]:
        return [e for e in self.written if query in e.content]


def _manager_with(*ids: str) -> PetManager:
    manager = PetManager()
    for session_id in ids:
        pet = PetSession(session_id=session_id, loop=FakeLoop())
        pet.start(PetTask(kind=PetTaskKind.IDLE_EXPLORATION, goal="观察环境"))
        manager.register(pet)
    return manager


# ---- status：结构化且不外泄 ----


def test_status_returns_structured_fields() -> None:
    control = PetControl(_manager_with("p1"))
    status = control.status("p1")
    assert status["session_id"] == "p1"
    assert status["state"] == PetSessionState.ACTIVE.value
    assert status["sleeping"] is False
    assert status["pending"] == 1
    assert status["wake_count"] == 0
    assert "fault" in status


def test_status_does_not_leak_preferences_or_tasks() -> None:
    pet = PetSession(session_id="p1", loop=FakeLoop(), memory=FakeMemory())
    pet.start(PetTask(kind=PetTaskKind.IDLE_EXPLORATION, goal="秘密任务"))
    pet.observe("editor:vim")
    manager = PetManager()
    manager.register(pet)

    status = PetControl(manager).status("p1")
    assert "preferences" not in status and "tasks" not in status
    assert "vim" not in str(status), "不外泄主人偏好"
    assert "秘密任务" not in str(status), "不外泄任务正文"


# ---- sleep / wake ----


def test_sleep_then_wake_roundtrip() -> None:
    manager = _manager_with("p1")
    control = PetControl(manager)
    assert "入睡" in control.sleep("p1")
    assert control.status("p1")["sleeping"] is True

    pet = manager.get("p1")
    assert pet is not None
    with pytest.raises(PetError) as exc_info:
        pet.wake()
    assert exc_info.value.code is PetErrorCode.PET_YIELDING, "休眠中唤醒被拒"

    assert "叫醒" in control.wake("p1")
    assert control.status("p1")["sleeping"] is False
    assert pet.wake().reply == "ok"


# ---- assign：换活（入队 + 自动唤醒） ----


def test_assign_enqueues_and_clears_sleeping() -> None:
    control = PetControl(_manager_with("p1"))
    control.sleep("p1")
    control.assign("整理收藏夹", session_id="p1")
    status = control.status("p1")
    assert status["sleeping"] is False, "assign 自动唤醒让行中的宠物"
    assert status["pending"] == 2  # noqa: PLR2004 — 初始 1 件 + assign 1 件


# ---- stop ----


def test_stop_terminates_session() -> None:
    manager = _manager_with("p1")
    assert "停止" in PetControl(manager).stop("p1")
    pet = manager.get("p1")
    assert pet is not None and pet.state is PetSessionState.TERMINATED


# ---- 寻址 ----


def test_single_pet_default_addressing() -> None:
    control = PetControl(_manager_with("only"))
    assert control.status()["session_id"] == "only"


def test_multiple_pets_without_id_rejected() -> None:
    control = PetControl(_manager_with("a", "b"))
    with pytest.raises(PetError) as exc_info:
        control.status()
    assert exc_info.value.code is PetErrorCode.PET_TARGET_AMBIGUOUS
    assert "a" in str(exc_info.value) and "b" in str(exc_info.value)


def test_unknown_session_rejected() -> None:
    control = PetControl(_manager_with("p1"))
    with pytest.raises(PetError) as exc_info:
        control.sleep("nope")
    assert exc_info.value.code is PetErrorCode.PET_NOT_FOUND


def test_no_pets_rejected() -> None:
    with pytest.raises(PetError) as exc_info:
        PetControl(PetManager()).status()
    assert exc_info.value.code is PetErrorCode.PET_NOT_FOUND
