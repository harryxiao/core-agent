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


def test_wake_notifies_owner_on_feedback_cycle() -> None:
    """账本 E16：唤醒收尾把既有 `report()` 产出真的投递给主人（反馈周期命中）。"""
    sent: list[str] = []
    session = PetSession(loop=FakeLoop(), notifier=sent.append, feedback_period=1)
    session.start(_task())
    session.wake()
    assert len(sent) == 1
    assert "宠物" in sent[0]


def test_wake_stays_silent_off_feedback_cycle() -> None:
    """未命中反馈周期不产出（不刷屏）：period=3 时前两次唤醒静默，第三次投递。"""
    sent: list[str] = []
    session = PetSession(loop=FakeLoop(), notifier=sent.append, feedback_period=3)
    session.start(_task())
    session.dispatch(_task())
    session.dispatch(_task())
    session.wake()
    session.wake()
    assert sent == []
    session.wake()
    assert len(sent) == 1


def test_wake_without_notifier_is_silent() -> None:
    """兜底不变：无 notifier 时唤醒照常完成且不报错。"""
    session = PetSession(loop=FakeLoop(), feedback_period=1)
    session.start(_task())
    assert session.wake().reply == "ok"


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
    session.dispatch(_task())
    session.observe("theme:dark")
    session.wake()  # 消费队首 ⇒ 队列剩 1
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


# ---- 惊喜：真实化与上报（change 0086 / 账本 E26 的 surprise 半边） ----


class _FailOnSecondCallLoop:
    """第 2 次调用抛错：用于证明惊喜失败时 fail-soft（唤醒不被拖垮）。"""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, user_input: str) -> LoopResult:
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("惊喜执行失败")
        return LoopResult(reply="ok", trace_id="t1")


def test_surprise_without_preference_returns_none() -> None:
    """无真实可代办前提 ⇒ 不产出（账本 E26：不以「已帮你安排」通用文案谎报）。"""
    session = PetSession(loop=FakeLoop())
    session.start(_task())
    assert session.surprise() is None


def test_surprise_with_preference_runs_loop_and_reports_real_result() -> None:
    """有偏好 ⇒ 经真实 loop 执行一次代办，回报**真实产出**（非通用文案）。"""
    loop = FakeLoop(reply="整理好了收藏夹")
    session = PetSession(loop=loop, memory=FakeMemory())
    session.start(_task())
    session.observe("theme:dark")
    before = len(loop.prompts)
    message = session.surprise()
    assert message is not None
    assert "theme" in message and "dark" in message
    assert "整理好了收藏夹" in message, "回报的是 loop 真实产出"
    assert len(loop.prompts) == before + 1, "惊喜经真实 loop 执行一次"


def test_wake_notifies_report_but_not_surprise_without_preference() -> None:
    """反馈周期命中但无偏好 ⇒ 只投周期反馈，无惊喜（不谎报）。"""
    sent: list[str] = []
    session = PetSession(loop=FakeLoop(), notifier=sent.append, feedback_period=1)
    session.start(_task())
    session.wake()
    assert len(sent) == 1
    assert "宠物" in sent[0]


def test_wake_reports_surprise_on_feedback_cycle_with_preference() -> None:
    """反馈周期命中且有偏好 ⇒ 反馈 + 惊喜两条（惊喜紧随反馈）。"""
    sent: list[str] = []
    session = PetSession(
        loop=FakeLoop(reply="已整理"), memory=FakeMemory(), notifier=sent.append, feedback_period=1
    )
    session.start(_task())
    session.observe("theme:dark")
    session.wake()
    assert len(sent) == 2  # noqa: PLR2004 — 反馈 + 惊喜两条
    assert "宠物" in sent[0]
    assert "可代办" in sent[1] and "已整理" in sent[1]


def test_wake_survives_surprise_failure() -> None:
    """惊喜是非关键路径：其 loop 失败不阻断唤醒（fail-soft）。"""
    sent: list[str] = []
    session = PetSession(
        loop=_FailOnSecondCallLoop(), memory=FakeMemory(), notifier=sent.append, feedback_period=1
    )
    session.start(_task())
    session.observe("theme:dark")
    assert session.wake().reply == "ok"
    assert len(sent) == 1, "惊喜失败 ⇒ 只投了周期反馈，未抛出"


# ---- 任务一次性与空闲自治睡眠（change 0087 / 账本 E26 的 microtask 半边） ----


def test_wake_consumes_dispatched_task() -> None:
    """唤醒**消费**队首任务（一次性）：队列由 2 → 1，被消费的是队首。"""
    loop = FakeLoop()
    session = PetSession(loop=loop)
    session.start(_task())
    session.dispatch(PetTask(kind=PetTaskKind.IDLE_EXPLORATION, goal="散步"))
    session.wake()
    assert len(session._tasks) == 1  # noqa: SLF001 — 出队断言
    assert session._tasks[0].goal == "散步"  # noqa: SLF001
    assert "收集今日新闻" in loop.prompts[0]


def test_wake_with_empty_queue_sleeps_and_rejects() -> None:
    """队列清空 ⇒ 入睡（让行态），不编造任务；后续唤醒被拒 PET_YIELDING。"""
    session = PetSession(loop=FakeLoop())
    session.start(_task())
    session.wake()
    assert session.snapshot()["yielding"] is True, "队列清空即进入休眠（让行态）"
    with pytest.raises(PetError) as exc_info:
        session.wake()
    assert exc_info.value.code is PetErrorCode.PET_YIELDING


def test_dispatch_auto_wakes_sleeping_pet() -> None:
    """新任务派发 ⇒ 自动唤醒（清让行态），下次唤醒消费该任务。"""
    session = PetSession(loop=FakeLoop())
    session.start(_task())
    session.wake()
    assert session.snapshot()["yielding"] is True
    session.dispatch(PetTask(kind=PetTaskKind.IDLE_EXPLORATION, goal="新活"))
    assert session.snapshot()["yielding"] is False
    assert session.wake().reply == "ok"


def test_idle_triggers_microtask_and_reports_real_output() -> None:
    """空闲入睡前经通知器上报微任务的**真实产出**（一次）。"""
    sent: list[str] = []
    session = PetSession(
        loop=FakeLoop(),
        notifier=sent.append,
        feedback_period=99,
        microtasks=lambda: "真实微任务产出",
    )
    session.start(_task())
    session.wake()
    assert sent == ["真实微任务产出"]


def test_idle_without_microtask_output_stays_silent() -> None:
    """微任务无真实产出（None）⇒ 不上报（不谎报）。"""
    sent: list[str] = []
    session = PetSession(
        loop=FakeLoop(), notifier=sent.append, feedback_period=99, microtasks=lambda: None
    )
    session.start(_task())
    session.wake()
    assert sent == []


def test_idle_microtask_failure_is_soft() -> None:
    """微任务异常被吞掉：照常入睡、不阻断唤醒（fail-soft）。"""

    def _boom() -> str | None:
        raise RuntimeError("微任务炸了")

    session = PetSession(
        loop=FakeLoop(), notifier=lambda _m: None, feedback_period=99, microtasks=_boom
    )
    session.start(_task())
    assert session.wake().reply == "ok"
    assert session.snapshot()["yielding"] is True
