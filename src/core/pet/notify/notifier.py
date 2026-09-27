"""异步通知主人（pet-notify）。

通知异步投递、不阻塞主循环（R13）：notify 仅入队立即返回，flush 才实际
投递；真实通道经 im（IMGateway）由宿主注入，deferred。

对应接口：doc/03-interfaces/pet-mode-interface.md §1（通知）+ spec R13
"""

from __future__ import annotations

from collections.abc import Callable


class AsyncNotifier:
    """异步通知：notify 只入队（不阻塞主循环），flush 才投递。"""

    def __init__(self, channel: Callable[[str], None] | None = None) -> None:
        self._channel = channel
        self._queue: list[str] = []

    def notify(self, message: str) -> None:
        """异步投递：仅入队立即返回，不阻塞主循环。"""
        self._queue.append(message)

    def flush(self) -> int:
        """实际投递队列中的通知；无通道时保留队列并返回 0。"""
        if self._channel is None:
            return 0
        for message in self._queue:
            self._channel(message)
        count = len(self._queue)
        self._queue.clear()
        return count

    @property
    def pending(self) -> list[str]:
        """当前待投递通知。"""
        return list(self._queue)
