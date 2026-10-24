"""TUI 退出及时性（change 0314）：守护线程执行器 + 显式 loop。

红线：Ctrl+Q 的退出耗时 SHALL NOT 随在途阻塞工作（LLM 流读取 / 工具执行）的剩余时长增长。
根因见 design §2：``asyncio.run`` 收尾的 ``shutdown_default_executor(wait=True)`` 会无限期
join 默认执行器线程。
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest

from core.ui import repl

_WAIT_LIMIT_S = 0.5  # 有界性断言上限（对照：阻塞工作 2s）
_ANSWER = 42  # 结果交付断言的哨兵值


def _release_after(event: threading.Event, seconds: float) -> None:
    """后台定时释放（让「会等待」的实现也能收尾，避免用例挂死）。"""

    def worker() -> None:
        time.sleep(seconds)
        event.set()

    threading.Thread(target=worker, daemon=True).start()


def test_daemon_executor_delivers_result() -> None:
    loop = asyncio.new_event_loop()
    loop.set_default_executor(repl._DaemonExecutor())
    try:
        outcome = loop.run_until_complete(loop.run_in_executor(None, lambda: 6 * 7))
    finally:
        loop.close()
    assert outcome == _ANSWER


def test_daemon_executor_propagates_exception() -> None:
    loop = asyncio.new_event_loop()
    loop.set_default_executor(repl._DaemonExecutor())
    try:
        with pytest.raises(ValueError, match="boom"):
            loop.run_until_complete(
                loop.run_in_executor(None, lambda: (_ for _ in ()).throw(ValueError("boom")))
            )
    finally:
        loop.close()


def test_daemon_executor_uses_daemon_threads() -> None:
    executor = repl._DaemonExecutor()
    assert executor.submit(threading.current_thread).result().daemon is True  # type: ignore[union-attr]


def test_daemon_executor_rejects_after_shutdown() -> None:
    executor = repl._DaemonExecutor()
    executor.shutdown()
    with pytest.raises(RuntimeError, match="shutdown"):
        executor.submit(int)


def test_executor_shutdown_does_not_wait_for_blocked_job() -> None:
    """核心回归：有界收尾 —— 在途 Job 卡住时 shutdown 立即返回。"""
    executor = repl._DaemonExecutor()
    release = threading.Event()
    executor.submit(release.wait)
    _release_after(release, 2.0)  # 对照：会 join 的实现约 2s 才返回
    started = time.monotonic()
    executor.shutdown(wait=True)
    elapsed = time.monotonic() - started
    assert elapsed < _WAIT_LIMIT_S


def test_run_repl_installs_daemon_executor_and_closes_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class _App:
        def run(self, *, loop: asyncio.AbstractEventLoop | None = None) -> None:
            assert loop is not None, "run_repl 必须显式传入自建 loop（change 0314）"
            seen["loop"] = loop
            seen["executor"] = loop._default_executor  # noqa: SLF001 — 无公开读取口

    monkeypatch.setattr(repl, "build_app", lambda api, sid="": _App())
    repl.run_repl(object(), "")  # type: ignore[arg-type]

    assert isinstance(seen["executor"], repl._DaemonExecutor)
    assert seen["loop"].is_closed() is True


def test_run_repl_does_not_wait_for_in_flight_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """退出即放弃：在途执行器任务不阻塞 run_repl 返回。"""
    release = threading.Event()
    started = threading.Event()

    def job() -> None:
        started.set()
        release.wait()

    class _App:
        def run(self, *, loop: asyncio.AbstractEventLoop | None = None) -> None:
            assert loop is not None
            executor = loop._default_executor  # noqa: SLF001 — 无公开读取口
            executor.submit(job)  # 在途工作（不建 asyncio future：循环关闭后无回调）
            assert started.wait(1.0)

    monkeypatch.setattr(repl, "build_app", lambda api, sid="": _App())
    began = time.monotonic()
    repl.run_repl(object(), "")  # type: ignore[arg-type]
    elapsed = time.monotonic() - began
    release.set()
    assert elapsed < 1.0
