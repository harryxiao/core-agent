"""pet-notify 单元测试（异步投递不阻塞主循环）。"""

from __future__ import annotations

from core.pet_notify import AsyncNotifier


def test_notify_enqueues_without_delivering() -> None:
    delivered: list[str] = []
    notifier = AsyncNotifier(channel=delivered.append)
    notifier.notify("发现插件 X")
    assert delivered == []
    assert notifier.pending == ["发现插件 X"]


def test_flush_delivers() -> None:
    delivered: list[str] = []
    notifier = AsyncNotifier(channel=delivered.append)
    notifier.notify("a")
    notifier.notify("b")
    assert notifier.flush() == 2  # noqa: PLR2004
    assert delivered == ["a", "b"]
    assert notifier.pending == []


def test_flush_without_channel_keeps_queue() -> None:
    notifier = AsyncNotifier()
    notifier.notify("保留")
    assert notifier.flush() == 0
    assert notifier.pending == ["保留"]
