"""宠物**最近任务结果查询**（change 0113 / phase-28 E46）。

背景（一手复核）：`PetSession.wake()` **已经** `return result`（`LoopResult`），`driver.py:67`
丢弃返回值（`WakingSession` Protocol 明写「驱动只取其副作用」）⇒ 会话只留 `_last_trace_id`，
正文无处可查。本 change 让 `wake()` 在**会话内**自留一份 `last_result`，并由控制面新增**独立**
查询动词 `result` 暴露。

硬边界（规格）：**`status` 返回面逐字不变**（`pet-mode/spec.md:249`/`:255` SHALL NOT 外泄主人偏好
与任务正文）—— 本文件含守护用例钉住六键集合；结果查询**只本进程、只最近一次、不落盘**。
"""

from __future__ import annotations

import pytest

from core.entry import _pet_control
from core.loop import LoopResult
from core.memory import MemoryEntry
from core.pet.core import (
    PetControl,
    PetError,
    PetErrorCode,
    PetManager,
    PetSession,
    PetTask,
    PetTaskKind,
)
from core.ui import UIAPILayer

_STATUS_KEYS = {"session_id", "state", "sleeping", "pending", "wake_count", "fault"}


class FakeLoop:
    """返回受控结果的 fake loop（复用 `test_pet_control` 同款）。"""

    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def run(self, user_input: str, *, session_id: str = "") -> LoopResult:
        self.prompts.append(user_input)
        return LoopResult(reply=self.reply, trace_id="t1")


class FakeMemory:
    def __init__(self) -> None:
        self.written: list[MemoryEntry] = []

    def write(self, layer: str, entry: MemoryEntry) -> str | None:
        self.written.append(entry)
        return entry.id

    def read(self, query: str, budget: int = 4096) -> list[MemoryEntry]:
        return [e for e in self.written if query in e.content]


def _manager_with(*ids: str, reply: str = "ok") -> PetManager:
    manager = PetManager()
    for session_id in ids:
        pet = PetSession(session_id=session_id, loop=FakeLoop(reply))
        pet.start(PetTask(kind=PetTaskKind.IDLE_EXPLORATION, goal="观察环境"))
        manager.register(pet)
    return manager


# ---- 查询面：最近一次任务结果 ----


def test_result_before_wake_reports_no_result() -> None:
    """未唤醒过 ⇒ 明确「无结果」，不编造正文（`reply` 为 None）。"""
    control = PetControl(_manager_with("p1"))
    result = control.result("p1")
    assert result["session_id"] == "p1"
    assert result["has_result"] is False
    assert result["reply"] is None
    assert result["failed"] is None


def test_result_after_wake_exposes_loop_reply() -> None:
    """唤醒一轮后 ⇒ 暴露 loop 返回的正文与成败（数据源 = 会话持有的 `last_result`）。"""
    manager = _manager_with("p1", reply="今天的观察：无事发生")
    pet = manager.get("p1")
    assert pet is not None
    pet.wake()
    result = PetControl(manager).result("p1")
    assert result["has_result"] is True
    assert result["reply"] == "今天的观察：无事发生"
    assert result["failed"] is False


def test_result_reflects_failed_run() -> None:
    """失败轮（`failed=True`）如实反映，不粉饰。"""
    manager = PetManager()
    pet = PetSession(session_id="p1", loop=_FailingLoop())
    pet.start(PetTask(kind=PetTaskKind.IDLE_EXPLORATION, goal="观察环境"))
    manager.register(pet)
    pet.wake()
    result = PetControl(manager).result("p1")
    assert result["has_result"] is True
    assert result["failed"] is True


class _FailingLoop:
    def run(self, user_input: str, *, session_id: str = "") -> LoopResult:
        return LoopResult(reply="", trace_id="t1", failed=True)


# ---- 守护：status 返回面逐字不变（隐私条款不得被本 change 松动） ----


def test_status_keys_unchanged_after_result_added() -> None:
    """`status` 键集合**逐字**等于既有六键；不因新增 result 面而变。"""
    manager = _manager_with("p1", reply="秘密正文")
    control = PetControl(manager)
    pet = manager.get("p1")
    assert pet is not None
    pet.wake()
    status = control.status("p1")
    assert set(status) == _STATUS_KEYS
    assert "秘密正文" not in str(status)


def test_status_does_not_leak_reply_even_when_result_exists() -> None:
    """有结果也不外泄：`status`/`snapshot` 过滤面（控制面）保持不含正文。"""
    manager = _manager_with("p1", reply="秘密正文")
    pet = manager.get("p1")
    assert pet is not None
    pet.wake()
    control = PetControl(manager)
    assert "reply" not in control.status("p1")
    assert "reply" not in pet.snapshot()  # 结果不进持久化面（只本进程）


# ---- 寻址：与既有控制动词逐字一致 ----


def test_result_single_pet_default_addressing() -> None:
    control = PetControl(_manager_with("only"))
    assert control.result()["session_id"] == "only"


def test_result_multiple_pets_without_target_rejected() -> None:
    control = PetControl(_manager_with("p1", "p2"))
    with pytest.raises(PetError) as exc_info:
        control.result()
    assert exc_info.value.code is PetErrorCode.PET_TARGET_AMBIGUOUS


def test_result_unknown_session_rejected() -> None:
    control = PetControl(_manager_with("p1"))
    with pytest.raises(PetError) as exc_info:
        control.result("nope")
    assert exc_info.value.code is PetErrorCode.PET_NOT_FOUND


# ---- CLI 面（`pet result` 分派） ----


def test_cli_pet_result_prints_reply(capsys: pytest.CaptureFixture[str]) -> None:
    manager = _manager_with("p1", reply="巡检结论：一切正常")
    pet = manager.get("p1")
    assert pet is not None
    pet.wake()
    assert _pet_control("result", [], manager) == 0
    out = capsys.readouterr().out
    assert "巡检结论：一切正常" in out
    assert "p1" in out


def test_cli_pet_result_no_result_is_honest(capsys: pytest.CaptureFixture[str]) -> None:
    manager = _manager_with("p1")
    assert _pet_control("result", [], manager) == 0
    out = capsys.readouterr().out
    assert "无" in out


def test_cli_pet_result_unknown_session_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    manager = _manager_with("p1")
    assert _pet_control("result", ["--session", "nope"], manager) == 1
    assert "nope" in capsys.readouterr().err


# ---- 会话状态无关性（结果留存不影响生命周期） ----


def test_result_survives_go_idle() -> None:
    """任务队列跑空 ⇒ 会话入睡（让行态），但**最近结果**仍在（不因入睡而丢）。"""
    manager = _manager_with("p1", reply="唯一一轮")
    pet = manager.get("p1")
    assert pet is not None
    pet.wake()
    assert pet.snapshot()["yielding"] is True  # 队列清空即入睡（复用语义，不新增枚举）
    assert PetControl(manager).result("p1")["reply"] == "唯一一轮"


# ---- UIAPI 面（前台 `/pet result`；与 CLI 复用同一 `PetControl`） ----


def test_ui_pet_command_result_uses_same_control() -> None:
    manager = _manager_with("p1", reply="前台可见的结论")
    pet = manager.get("p1")
    assert pet is not None
    pet.wake()
    api = UIAPILayer(pet_control=PetControl(manager))
    assert api.pet_command("result", session_id="p1")["reply"] == "前台可见的结论"
