"""遥测导出器（Exporter）。

导出器是可插拔的 :class:`Exporter` 协议实现：JSONL 落盘、控制台打印、
no-op 兜底。遥测故障**绝不阻塞主循环**——:class:`BufferedExporter` 把
导出失败降级为内存缓冲 + 溢出兜底 + 指数退避重试（时间门控，非阻塞）。
OTel/Prometheus 导出经同一协议接入（Phase 0 缺省 no-op，不引入第三方依赖）。

对应接口：doc/03-interfaces/observability-interface.md §5
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from .events import TraceEvent


class Exporter(Protocol):
    """导出器协议：一次性导出批量事件。"""

    def emit(self, events: list[TraceEvent]) -> None: ...


class JSONLExporter:
    """逐事件写入 JSONL 文件（追加模式），每行一条结构化事件。"""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def emit(self, events: list[TraceEvent]) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            for event in events:
                fh.write(json.dumps(asdict(event), ensure_ascii=False, default=str) + "\n")


class ConsoleExporter:
    """打印到 stdout，便于本地调试。"""

    def emit(self, events: list[TraceEvent]) -> None:
        for event in events:
            print(f"[{event.kind}] {event.trace_id}:{event.span_id} {event.payload}")


class NoopExporter:
    """no-op 兜底：遥测未启用或 OTel 未接入时不阻塞、不落盘。"""

    def emit(self, events: list[TraceEvent]) -> None:
        return None


class BufferedExporter:
    """带内存缓冲、溢出兜底与指数退避重试的导出器装饰器。

    导出失败时事件滞留内存缓冲（降级、不阻塞主循环）；缓冲逼近上限按
    FIFO 丢弃最旧低价值事件兜底；重试按指数退避时间门控，退避期内跳过
    重试，主循环照常推进。
    """

    def __init__(
        self,
        inner: Exporter,
        *,
        capacity: int = 1000,
        backoff_base: float = 0.5,
        max_backoff: float = 30.0,
    ) -> None:
        self._inner = inner
        self._capacity = capacity
        self._backoff_base = backoff_base
        self._max_backoff = max_backoff
        self._buffer: list[TraceEvent] = []
        self._degraded = False
        self._dropped = 0
        self._next_retry = 0.0
        self._delay = backoff_base

    def emit(self, events: list[TraceEvent]) -> None:
        for event in events:
            if len(self._buffer) >= self._capacity:
                self._buffer.pop(0)
                self._dropped += 1
            self._buffer.append(event)
        self.flush()

    def flush(self) -> None:
        """尽力导出缓冲；退避期内或导出失败时不抛异常、不阻塞主循环。"""
        if not self._buffer:
            return
        now = time.time()
        if now < self._next_retry:
            return
        try:
            self._inner.emit(list(self._buffer))
            self._buffer.clear()
            self._degraded = False
            self._delay = self._backoff_base
        except Exception:  # noqa: BLE001 — 导出失败降级，绝不抛给主循环
            self._degraded = True
            self._next_retry = now + self._delay
            self._delay = min(self._delay * 2, self._max_backoff)

    @property
    def degraded(self) -> bool:
        return self._degraded

    @property
    def dropped(self) -> int:
        return self._dropped
