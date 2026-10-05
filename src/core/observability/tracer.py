"""链路追踪（Tracer）与全链路日志采集（TraceLogger）。

Tracer 为每个任务分配 ``trace_id``，贯穿执行全链路：``start_trace`` 建链、
``record`` 追加事件、``end_trace`` **封口**（事件交付导出器并从内存释放）。
Tracer 只保留**在途**（未封口）链路的事件，故其内存占用不随已封口 trace 数
增长；``replay`` 服务在途链路，**已完成**任务的事后回溯以**落盘遥测**为真源。
TraceLogger 在其上记录模型 IO / 工具调用 / 副作用三类事件，写入前经
:class:`Redactor` 脱敏。

对应接口：doc/03-interfaces/observability-interface.md §2 / §4
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from .events import TraceEvent
from .exporter import Exporter, NoopExporter
from .redaction import Redactor


class Tracer:
    """事件存储与链路生命周期：start_trace / end_trace / replay（只保在途链路）。"""

    def __init__(self, exporter: Exporter | None = None, redactor: Redactor | None = None) -> None:
        self._events: dict[str, list[TraceEvent]] = {}
        self._exporter = exporter if exporter is not None else NoopExporter()
        self._redactor = redactor if redactor is not None else Redactor()

    def register_secret(self, value: str) -> None:
        """登记明文密钥，遥测写入前脱敏（与 coeffect secret 标记联动）。"""
        self._redactor.register_secret(value)

    def start_trace(self, task_id: str) -> str:
        """开启一条 trace，返回贯穿全链路的 trace_id。"""
        trace_id = uuid.uuid4().hex
        self._events[trace_id] = []
        return trace_id

    def end_trace(self, trace_id: str) -> None:
        """**封口** trace：交付该链路事件给导出器（落盘为真源）并**释放内存**。

        导出失败不阻塞（见 Exporter）。封口后该链路不再驻留内存，事后回溯一律以
        导出器产出（如 JSONL）为真源。调用方 SHALL 在需要读取本轮事件者（如
        evolution 冷路径回调）**之后**再封口。
        """
        events = self._events.pop(trace_id, [])
        if events:
            self._exporter.emit(events)

    def replay(self, trace_id: str) -> list[TraceEvent]:
        """按时间序重放**在途**（未封口）链路的全部事件，支持执行中定位失败环节。

        已完成（已封口）链路的回溯请读取导出器产出（落盘遥测）——本方法返回空。
        """
        return sorted(self._events.get(trace_id, []), key=lambda e: e.ts)

    def record(self, event: TraceEvent) -> None:
        """内部：脱敏后写入事件缓冲（不即时导出，由 end_trace 统一导出）。"""
        event.payload = self._redactor.redact(event.payload)
        self._events.setdefault(event.trace_id, []).append(event)


class TraceLogger:
    """在 Tracer 上记录模型 IO / 工具调用 / 副作用三类结构化事件。"""

    def __init__(self, tracer: Tracer) -> None:
        self._tracer = tracer

    def log_model_io(self, trace_id: str, prompt: str, completion: str, latency_ms: float) -> None:
        """记录模型输入/输出（密钥脱敏）。"""
        self._emit(
            trace_id,
            "model_io",
            {"prompt": prompt, "completion": completion, "latency_ms": latency_ms},
        )

    def log_tool_call(
        self,
        trace_id: str,
        tool: str,
        args: dict[str, Any] | str,
        result: dict[str, Any],
        latency_ms: float,
    ) -> None:
        """记录工具调用参数/结果/耗时。

        ``args`` 允许为节选字符串（超长参数按调用方节选口径截断）⇒ 事件面有界。
        """
        self._emit(
            trace_id,
            "tool_call",
            {"tool": tool, "args": args, "result": result, "latency_ms": latency_ms},
        )

    def log_effect(self, trace_id: str, effect: dict[str, Any]) -> None:
        """关联副作用记录。"""
        self._emit(trace_id, "effect", {"effect": effect})

    def _emit(self, trace_id: str, kind: str, payload: dict[str, Any]) -> None:
        event = TraceEvent(
            trace_id=trace_id,
            span_id=uuid.uuid4().hex,
            ts=time.time(),
            kind=kind,
            payload=payload,
        )
        self._tracer.record(event)
