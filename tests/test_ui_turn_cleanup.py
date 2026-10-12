"""TUI 回合收尾异常安全化（change 0231）。

不变式：**忙态复位不受呈现收尾失败影响** —— 任一次瞬时收尾错误都不得使 UI 永久拒收输入。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from core.configuration.models import LLMConfig
from core.loop import LoopEvent
from core.ui import UIAPILayer
from core.ui.repl import build_app


def _llm() -> LLMConfig:
    return LLMConfig(provider="openai", model="gpt-4o", endpoint="https://x", api_key_ref="${K}")


class _EchoLoop:
    """回显 loop 替身：记录输入并一次性收尾。"""

    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def astream(self, user_input: str, *, session_id: str = ""):
        self.inputs.append(user_input)
        yield LoopEvent("loop_finished", {"reply": f"echo:{user_input}"})


class _TaskOrch:
    """任务编排器桩：立即收尾。"""

    async def astream(self, task_id: str, goal: str, **kwargs: object):
        yield LoopEvent("task_finished", {"outcomes": []})


def _app(*, orch: Any = None) -> Any:
    api = UIAPILayer(loop=_EchoLoop(), orchestrator=orch)
    api.set_llm_config(_llm())
    return build_app(api)


def _raiser(_msg: str = "boom") -> Any:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(_msg)

    return _boom


# ---- 单元：_end_turn 不变式 ----


def test_end_turn_resets_busy_when_flush_live_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """承重：呈现收尾 `_flush_live` 抛错，忙态仍须复位。"""
    app = _app()
    app._turn_busy = True
    monkeypatch.setattr(app, "_flush_live", _raiser("flush boom"))
    app._end_turn(flush_live=True)
    assert app._turn_busy is False


def test_end_turn_resets_busy_when_spin_stop_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """状态行收尾 `_spin_stop` 抛错，忙态仍须复位。"""
    app = _app()
    app._turn_busy = True
    monkeypatch.setattr(app, "_spin_stop", _raiser("spin boom"))
    app._end_turn()
    assert app._turn_busy is False


# ---- 集成：三个 runner 的收尾失败均不影响忙态复位 ----


def test_turn_resets_busy_when_spin_stop_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """普通轮：状态行收尾抛错 ⇒ 轮后忙态复位（不再永久卡死）。"""
    app = _app()
    monkeypatch.setattr(app, "_spin_stop", _raiser())

    async def drive() -> None:
        async with app.run_test() as pilot:
            await pilot.press("h", "i", "enter")
            for _ in range(30):
                await pilot.pause()
            assert app._turn_busy is False

    asyncio.run(drive())


def test_task_turn_resets_busy_when_spin_stop_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """任务轮：状态行收尾抛错 ⇒ 轮后忙态复位。"""
    app = _app(orch=_TaskOrch())
    monkeypatch.setattr(app, "_spin_stop", _raiser())

    async def drive() -> None:
        async with app.run_test() as pilot:
            for ch in "/task 查答案":
                await pilot.press(ch)
            await pilot.press("enter")
            for _ in range(30):
                await pilot.pause()
            assert app._turn_busy is False

    asyncio.run(drive())


def test_beast_turn_resets_busy_when_spin_stop_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """神兽轮：状态行收尾抛错 ⇒ 轮后忙态复位（无激活器时走既有 UiError 降级，收尾仍复位）。"""
    app = _app()
    monkeypatch.setattr(app, "_spin_stop", _raiser())

    async def drive() -> None:
        async with app.run_test() as pilot:
            for ch in "/summon 小狗":
                await pilot.press(ch)
            await pilot.press("enter")
            for _ in range(30):
                await pilot.pause()
            assert app._turn_busy is False

    asyncio.run(drive())


# ---- 分发口：worker 启动失败不得遗留忙态 ----


def test_dispatch_failure_resets_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    """`run_worker` 抛错（派发失败）⇒ 忙态复位（异常仍冒泡，崩溃可见性不变）。"""
    app = _app()
    boom_msg = "run_worker boom"

    def _boom(coro: Any) -> None:  # 真 run_worker 会调度该协程；桩先关闭再抛，避免孤儿告警
        coro.close()
        raise RuntimeError(boom_msg)

    monkeypatch.setattr(app, "run_worker", _boom)

    async def drive() -> bool:
        try:
            async with app.run_test() as pilot:
                await pilot.press("h", "i", "enter")
                for _ in range(10):
                    await pilot.pause()
                return app._turn_busy
        except RuntimeError:  # 派发失败在 handler / app 退出时冒泡：守卫须已复位忙态
            return app._turn_busy

    assert asyncio.run(drive()) is False
