"""可观测性与遥测（observability）。

日志 / 指标 / 链路追踪三根支柱：让智能体每一步执行可追溯、可复盘，同时
作为进化引擎诊断与评测的数据源。遥测自身故障（导出失败 / 缓冲溢出）绝不
阻塞主循环——降级为内存缓冲 + 溢出兜底 + 指数退避重试。

OTel/Prometheus 导出经 :class:`Exporter` 协议接入（Phase 0 缺省 no-op）。

对应规格：doc/openspec/specs/observability/spec.md
"""

from .errors import ErrorCode, TelemetryError
from .events import TraceEvent
from .exporter import (
    BufferedExporter,
    ConsoleExporter,
    Exporter,
    JSONLExporter,
    NoopExporter,
)
from .metrics import MetricsCollector
from .redaction import Redactor
from .tracer import TraceLogger, Tracer

__all__ = [
    "BufferedExporter",
    "ConsoleExporter",
    "ErrorCode",
    "Exporter",
    "JSONLExporter",
    "MetricsCollector",
    "NoopExporter",
    "Redactor",
    "TelemetryError",
    "TraceEvent",
    "TraceLogger",
    "Tracer",
]
