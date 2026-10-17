"""pet 故障韧性与人格固定（change 0250 / ADR-0240）。

三处生产可达缺陷的回归面：人格跨进程丢失、唤醒进度不落盘、唤醒异常无退避/无恢复。
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path

import pytest

from core.configuration import ConfigManager
from core.loop import LoopResult
from core.pet.core import (
    FAILED,
    WOKEN,
    PetControl,
    PetManager,
    PetSession,
    PetSessionState,
    PetTask,
    PetTaskKind,
    PetWakeDriver,
    WakeOutcome,
)
from core.pet.library.persona import Persona, persona_from_record
from core.runtime import build_runtime


class FakeLoop:
    """记录 prompt 的 fake loop；``fail`` 为真时唤醒抛异常。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.prompts: list[str] = []

    def run(self, user_input: str, *, session_id: str = "") -> LoopResult:
        self.prompts.append(user_input)
        if self.fail:
            raise RuntimeError("boom")
        return LoopResult(reply="ok", trace_id="t1")

    async def arun(self, user_input: str, *, session_id: str = "") -> LoopResult:
        return self.run(user_input, session_id=session_id)


PERSONA = Persona(
    name="小橘",
    species="猫",
    persona_text="安静陪伴主人工作。",
    traits=["慵懒", "敏锐"],
    preferences=["晒太阳"],
)


def _task(goal: str = "收集新闻") -> PetTask:
    return PetTask(kind=PetTaskKind.INFORMATION_GATHERING, goal=goal)


def _factory(record: dict[str, object]) -> PetSession:
    return PetSession.restore(record, persona_factory=persona_from_record)


# ---- 人格固定 ----


def test_snapshot_carries_persona_and_restore_rebuilds_it() -> None:
    session = PetSession(loop=FakeLoop(), persona=PERSONA)
    snap = session.snapshot()
    assert snap["persona"] == {
        "name": "小橘",
        "species": "猫",
        "persona_text": "安静陪伴主人工作。",
        "traits": ["慵懒", "敏锐"],
        "preferences": ["晒太阳"],
    }
    restored = PetSession.restore(snap, loop=FakeLoop(), persona_factory=persona_from_record)
    restored.start(_task())
    restored.wake()
    prompt = restored._loop.prompts[0]  # noqa: SLF001 — 断言人格真的进入 prompt
    assert prompt == f"{PERSONA.render_prompt()}\n任务：收集新闻"


def test_explicit_persona_wins_over_snapshot() -> None:
    session = PetSession(loop=FakeLoop(), persona=PERSONA)
    snap = session.snapshot()
    other = Persona(name="阿黄", species="狗", persona_text="热情。")
    restored = PetSession.restore(
        snap, loop=FakeLoop(), persona=other, persona_factory=persona_from_record
    )
    restored.start(_task())
    restored.wake()
    assert "阿黄" in restored._loop.prompts[0]  # noqa: SLF001
    assert "小橘" not in restored._loop.prompts[0]  # noqa: SLF001


def test_bare_session_stays_bare_after_roundtrip() -> None:
    """无人格会话逐字不变：snapshot 记 None，恢复后 prompt 仍是裸任务。"""
    session = PetSession(loop=FakeLoop())
    snap = session.snapshot()
    assert snap["persona"] is None
    restored = PetSession.restore(snap, loop=FakeLoop(), persona_factory=persona_from_record)
    restored.start(_task())
    restored.wake()
    assert restored._loop.prompts == ["收集新闻"]  # noqa: SLF001


# ---- 唤醒故障韧性 ----


def test_wake_failure_enters_backoff_and_reraises() -> None:
    loop = FakeLoop(fail=True)
    session = PetSession(loop=loop)
    session.start(_task())
    with pytest.raises(RuntimeError, match="boom"):
        session.wake()
    assert session.state is PetSessionState.BACKOFF
    snap = session.snapshot()
    assert "boom" in snap["fault"]
    # 一次性语义：失败任务不回队（重派由主人/控制面决定）
    assert snap["tasks"] == []


def test_wake_cancelled_error_does_not_backoff() -> None:
    """取消/中断不是会话故障：``CancelledError`` 不置 BACKOFF（也不吞）。"""

    class CancellingLoop(FakeLoop):
        async def arun(self, user_input: str, *, session_id: str = "") -> LoopResult:
            raise asyncio.CancelledError

    session = PetSession(loop=CancellingLoop())
    session.start(_task())
    with pytest.raises(asyncio.CancelledError):
        session.wake()
    assert session.state is PetSessionState.ACTIVE


def test_control_wake_recovers_backoff_session() -> None:
    loop = FakeLoop(fail=True)
    manager = PetManager()
    session = PetSession(loop=loop)
    manager.register(session)
    session.start(_task())
    with pytest.raises(RuntimeError):
        session.wake()
    assert session.state is PetSessionState.BACKOFF

    control = PetControl(manager)
    control.wake(session.session_id)
    assert session.state is PetSessionState.ACTIVE
    assert session.snapshot()["fault"] == ""

    loop.fail = False
    session.dispatch(_task("收集天气"))
    assert session.wake().reply == "ok"


def test_control_wake_on_active_session_keeps_resume_semantics() -> None:
    """非 BACKOFF 会话仍走既有 `resume()`：先睡后醒逐字不变。"""
    session = PetSession(loop=FakeLoop())
    manager = PetManager()
    manager.register(session)
    session.start(_task())
    control = PetControl(manager)
    control.sleep(session.session_id)
    assert session.snapshot()["yielding"] is True
    control.wake(session.session_id)
    assert session.snapshot()["yielding"] is False


# ---- 落盘边界 ----


def test_control_assign_persists_registry(tmp_path: Path) -> None:
    path = tmp_path / "pets.json"
    manager = PetManager(path, factory=_factory)
    session = PetSession(loop=FakeLoop(), persona=PERSONA)
    manager.register(session)
    session.start(_task())
    PetControl(manager).assign("看看日志", session_id=session.session_id)

    fresh = PetManager(path, factory=_factory)
    restored = fresh.get(session.session_id)
    assert restored is not None
    snap = restored.snapshot()
    assert [t["goal"] for t in snap["tasks"]] == ["收集新闻", "看看日志"]
    assert snap["yielding"] is False
    assert snap["persona"]["name"] == "小橘"


def test_wake_progress_persists_across_processes(tmp_path: Path) -> None:
    """persist 落在每次驱动 tick：已消费任务不复活、唤醒计数不归零。"""
    path = tmp_path / "pets.json"
    manager = PetManager(path, factory=_factory)
    session = PetSession(loop=FakeLoop(), persona=PERSONA, feedback_period=99)
    manager.register(session)
    session.start(_task("任务一"))
    session.dispatch(_task("任务二"))
    session.wake()
    manager.persist()  # 驱动 on_tick 的落盘边界

    restored = PetManager(path, factory=_factory).get(session.session_id)
    assert restored is not None
    snap = restored.snapshot()
    assert [t["goal"] for t in snap["tasks"]] == ["任务二"]
    assert snap["wake_count"] == 1
    assert snap["persona"]["persona_text"] == "安静陪伴主人工作。"


def test_runtime_restore_factory_pins_persona(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """组合根恢复工厂必须重建人格（激活进程与新进程同一人格）。"""
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n"
        "  reasoning_effort: low\n",
        encoding="utf-8",
    )
    manager = ConfigManager(yaml_path=str(cfg))
    first = build_runtime(manager)
    session = first.pet_activator.activate_from_cli("gather", ["今日新闻"], persona=PERSONA)
    session_id = session.session_id

    second = build_runtime(manager)
    restored = second.pet_manager.get(session_id)
    assert restored is not None
    assert restored._persona is not None  # noqa: SLF001 — 恢复工厂断言
    assert restored._persona.render_prompt() == PERSONA.render_prompt()  # noqa: SLF001


def test_wake_outcomes_still_isolated_per_pet() -> None:
    """驱动面契约不变：一只宠物异常 ⇒ 其余照常唤醒（R8）。"""

    class Flaky:
        session_id = "a"

        def wake(self) -> object:
            raise RuntimeError("boom")

    class Fine:
        session_id = "b"

        def wake(self) -> object:
            return None

    outcomes: list[WakeOutcome] = PetWakeDriver(lambda: [Flaky(), Fine()]).tick()
    assert [(o.session_id, o.status) for o in outcomes] == [("a", FAILED), ("b", WOKEN)]


def test_driver_iterable_reload_is_used() -> None:
    """驱动每轮重取会话列表（落盘边界依赖它看到最新注册），此处只锁契约。"""
    calls: list[int] = []

    def sessions() -> Iterable[object]:
        calls.append(1)
        return []

    driver = PetWakeDriver(sessions)
    driver.tick()
    driver.tick()
    assert len(calls) == 2  # noqa: PLR2004 — 两轮 tick 各取一次
