"""TUI 优雅退出接缝（change 0315）：`flush_post_turn` 的有界等待与 API 委托。

红线：`/exit` 等待的收尾链 SHALL 有界（复用既有轮末上限），超时不取消任务、不挂死；
Ctrl+Q 的立即退出语义由 0314 用例钉住，本文件不重复。
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest

from core.loop import Action, DefaultLoop
from core.tools import ToolProvider
from core.ui import UIAPILayer, UiError, UiErrorCode

_WAIT_LIMIT_S = 1.0  # 有界性断言上限（对照：阻塞观察者 5s）


def _reply_loop(**kwargs: Any) -> DefaultLoop:
    """跑一轮即终止的 loop（无工具动作，供后台收尾链断言）。"""

    def planner(ctx: Any) -> Action:
        return Action(args={"reply": "done"})

    return DefaultLoop(planner=planner, tools=ToolProvider(), max_rounds=1, **kwargs)


def _blocking_observer(entered: threading.Event, release: threading.Event) -> Any:
    """阻塞式轮末观察者：进入即 set，直到 release 才返回。"""

    def observer(task: str, steps: list[str], ok: bool, reply: str) -> None:
        entered.set()
        release.wait(timeout=5.0)

    return observer


def test_flush_post_turn_waits_for_background_chain() -> None:
    """后台收尾在途 ⇒ `flush_post_turn()` 等其收束后返回 True。"""
    entered = threading.Event()
    release = threading.Event()

    async def main() -> bool:
        loop = _reply_loop(turn_observer=_blocking_observer(entered, release))
        async for _ in loop.astream("one"):
            pass
        assert await asyncio.to_thread(entered.wait, 2.0), "轮末收尾确已进入阻塞"
        flush_task = asyncio.create_task(loop.flush_post_turn())
        await asyncio.sleep(0.05)
        assert not flush_task.done(), "收尾未收束前不应返回"
        release.set()
        return await asyncio.wait_for(flush_task, 2.0)

    assert asyncio.run(main()) is True


def test_flush_post_turn_is_bounded_and_keeps_task_running() -> None:
    """等待上限越界 ⇒ 及时返回 False，且不取消收尾 task（放行后仍可收束）。"""
    entered = threading.Event()
    release = threading.Event()

    async def main() -> tuple[bool, float, bool]:
        loop = _reply_loop(
            turn_observer=_blocking_observer(entered, release),
            post_turn_wait_timeout=0.1,
        )
        async for _ in loop.astream("one"):
            pass
        assert await asyncio.to_thread(entered.wait, 2.0)
        started = time.monotonic()
        settled = await loop.flush_post_turn()
        elapsed = time.monotonic() - started
        release.set()
        again = await loop.flush_post_turn(timeout=2.0)  # 未取消 ⇒ 收束后可再等到 True
        return settled, elapsed, again

    settled, elapsed, again = asyncio.run(main())
    assert settled is False
    assert elapsed < _WAIT_LIMIT_S
    assert again is True


def test_flush_post_turn_without_pending_returns_true() -> None:
    """无在途收尾 ⇒ 立即 True（空闲退出不等待）。"""
    assert asyncio.run(_reply_loop().flush_post_turn()) is True


class _FlushLoop:
    """仅提供收尾接缝的 loop 替身。"""

    def __init__(self, settled: bool) -> None:
        self.settled = settled
        self.calls = 0

    async def flush_post_turn(self) -> bool:
        self.calls += 1
        return self.settled


def test_api_flush_post_turn_delegates_to_loop() -> None:
    """API 委托到 loop 的接缝并透传布尔。"""
    loop = _FlushLoop(settled=False)
    api = UIAPILayer(loop=loop)  # type: ignore[arg-type]
    sid = api.create_session("cli")
    assert asyncio.run(api.flush_post_turn(sid)) is False
    assert loop.calls == 1


def test_api_flush_post_turn_without_seam_returns_true() -> None:
    """自定义 loop 无该接缝 ⇒ 视为无在途收尾（不报错）。"""
    api = UIAPILayer(loop=object())  # type: ignore[arg-type]
    sid = api.create_session("cli")
    assert asyncio.run(api.flush_post_turn(sid)) is True


def test_api_flush_post_turn_requires_session() -> None:
    """未登记会话 fail-closed（不放宽会话校验）。"""
    api = UIAPILayer(loop=_FlushLoop(settled=True))  # type: ignore[arg-type]
    with pytest.raises(UiError) as err:
        asyncio.run(api.flush_post_turn("missing"))
    assert err.value.code is UiErrorCode.UI_SESSION_NOT_FOUND
