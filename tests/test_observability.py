"""observability 单元测试（对齐规格场景 + M0 验收）。

覆盖 spec/observability 的场景：
- 模型/工具/effect 三类事件记录（结构化，含 trace_id/span_id/ts）
- 敏感信息脱敏（SecretRef 句柄 + 明文登记 + 敏感键名兜底）
- 指标 inc/gauge/snapshot 按 tags 聚合
- 单任务全链路回溯（start/end + replay 时间序）
- JSONL 落盘、no-op 兜底
- 遥测故障不阻塞主循环：导出失败降级 + 缓冲溢出兜底 + 指数退避
"""

from __future__ import annotations

import json

from core.observability import (
    BufferedExporter,
    ErrorCode,
    JSONLExporter,
    MetricsCollector,
    NoopExporter,
    TelemetryError,
    TraceEvent,
    TraceLogger,
    Tracer,
)


class _FailingExporter:
    """导出始终失败的桩：模拟磁盘满 / 下游不可达。"""

    def emit(self, events: list[TraceEvent]) -> None:
        raise OSError


class _CapturingExporter:
    """收集已交付事件的桩：证明封口真把事件交付导出器（落盘真路径）。"""

    def __init__(self) -> None:
        self.batches: list[list[TraceEvent]] = []

    def emit(self, events: list[TraceEvent]) -> None:
        self.batches.append(list(events))

    @property
    def events(self) -> list[TraceEvent]:
        return [event for batch in self.batches for event in batch]


def _event(span_id: str, ts: float = 0.0) -> TraceEvent:
    return TraceEvent(trace_id="t1", span_id=span_id, ts=ts, kind="metric", payload={})


def test_trace_event_fields() -> None:
    event = TraceEvent(
        trace_id="t1", span_id="s1", ts=1.5, kind="model_io", payload={"prompt": "hi"}
    )
    assert event.trace_id == "t1"
    assert event.span_id == "s1"
    assert event.ts == 1.5  # noqa: PLR2004
    assert event.kind == "model_io"
    assert event.payload == {"prompt": "hi"}


def test_trace_event_module_id_defaults_to_none() -> None:
    """模块归因字段可选：既有构造（不传 module_id）逐字不变，缺省为空。"""
    event = _event("s1")

    assert event.module_id is None, "未携带模块归因 ⇒ 缺省为空（向后兼容）"


def test_trace_event_carries_module_attribution() -> None:
    """事件可携带模块归因（供按模块聚合与缺陷归因）。"""
    event = TraceEvent(
        trace_id="t1",
        span_id="s1",
        ts=0.0,
        kind="loop_finished",
        payload={"failed": True},
        module_id="loop.default",
    )

    assert event.module_id == "loop.default"


def test_three_event_kinds_logged(tmp_path) -> None:
    exporter = JSONLExporter(tmp_path / "events.jsonl")
    tracer = Tracer(exporter=exporter)
    logger = TraceLogger(tracer)
    trace_id = tracer.start_trace("task-1")
    logger.log_model_io(trace_id, "prompt", "completion", 10.0)
    logger.log_tool_call(trace_id, "code_run", {"cmd": "ls"}, {"ok": True}, 5.0)
    logger.log_effect(trace_id, {"op": "file_write", "target": "/tmp/x"})
    tracer.end_trace(trace_id)
    # change 0103：封口即释放内存 ⇒ 回溯以**落盘**为真源
    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    assert [e["kind"] for e in events] == ["model_io", "tool_call", "effect"]
    assert all(e["trace_id"] == trace_id for e in events)
    assert all(e["span_id"] for e in events)


def test_secret_redaction_by_registration(tmp_path) -> None:
    exporter = JSONLExporter(tmp_path / "events.jsonl")
    tracer = Tracer(exporter=exporter)
    tracer.register_secret("sk-live-secret")
    logger = TraceLogger(tracer)
    trace_id = tracer.start_trace("task-1")
    logger.log_model_io(trace_id, "use key sk-live-secret now", "ok", 1.0)
    tracer.end_trace(trace_id)
    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    assert "sk-live-secret" not in text  # 真实密钥绝不落盘
    assert "<redacted>" in text


def test_secret_key_name_heuristic(tmp_path) -> None:
    tracer = Tracer(exporter=JSONLExporter(tmp_path / "events.jsonl"))
    logger = TraceLogger(tracer)
    trace_id = tracer.start_trace("task-1")
    logger.log_tool_call(trace_id, "http", {"api_key": "sk-raw"}, {"ok": True}, 1.0)
    tracer.end_trace(trace_id)
    text = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    assert "sk-raw" not in text  # 敏感键名命中即脱敏


def test_replay_time_ordered() -> None:
    tracer = Tracer()
    logger = TraceLogger(tracer)
    trace_id = tracer.start_trace("t")
    logger.log_tool_call(trace_id, "code_run", {"cmd": "ls"}, {"ok": True}, 1.0)
    logger.log_effect(trace_id, {"op": "file_write"})
    events = tracer.replay(trace_id)
    assert len(events) == 2  # noqa: PLR2004
    assert events[0].ts <= events[1].ts  # 按时间序


def test_end_trace_exports_jsonl(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    tracer = Tracer(exporter=JSONLExporter(path))
    logger = TraceLogger(tracer)
    trace_id = tracer.start_trace("t")
    logger.log_model_io(trace_id, "p", "c", 1.0)
    tracer.end_trace(trace_id)
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1
    assert set(lines[0]) >= {"trace_id", "span_id", "ts", "kind", "payload"}


# ---- change 0103：封口交付导出器 + 释放内存 ----


def test_end_trace_releases_in_flight_events() -> None:
    """封口后该 trace 不再驻留内存（在途可回放、封口即释放）。"""
    tracer = Tracer()
    logger = TraceLogger(tracer)
    trace_id = tracer.start_trace("t")
    logger.log_tool_call(trace_id, "code_run", {"cmd": "ls"}, {"ok": True}, 1.0)

    assert [e.kind for e in tracer.replay(trace_id)] == ["tool_call"], "封口前在途可回放"

    tracer.end_trace(trace_id)

    assert tracer.replay(trace_id) == [], "封口即释放内存"


def test_end_trace_delivers_events_to_exporter() -> None:
    """封口把事件交付导出器（落盘真路径），并释放内存。"""
    exporter = _CapturingExporter()
    tracer = Tracer(exporter=exporter)
    logger = TraceLogger(tracer)
    trace_id = tracer.start_trace("t")
    logger.log_model_io(trace_id, "p", "c", 1.0)

    tracer.end_trace(trace_id)

    assert [e.kind for e in exporter.events] == ["model_io"], "事件真被交付导出器"
    assert tracer.replay(trace_id) == [], "交付后释放"


def test_in_flight_memory_does_not_grow_across_traces() -> None:
    """连续开/封口多条 trace，内存不随已封口数增长（泄漏修复）。"""
    tracer = Tracer()
    logger = TraceLogger(tracer)
    for i in range(10):
        trace_id = tracer.start_trace(f"t{i}")
        logger.log_effect(trace_id, {"op": "file_write"})
        tracer.end_trace(trace_id)

    assert tracer._events == {}, "已封口 trace 不驻留"  # noqa: SLF001 — 内存有界断言


def test_metrics_inc_gauge_snapshot() -> None:
    m = MetricsCollector()
    m.inc("token.used", 100.0, tags={"plugin_id": "llm"})
    m.inc("token.used", 50.0, tags={"plugin_id": "llm"})
    m.gauge("loop.rounds", 3.0, tags={"plugin_id": "llm"})
    m.inc("token.used", 10.0, tags={"plugin_id": "mem"})
    snap = m.snapshot(tags={"plugin_id": "llm"})
    assert snap["token.used"] == 150.0  # noqa: PLR2004
    assert snap["loop.rounds"] == 3.0  # noqa: PLR2004
    assert m.snapshot(tags={"plugin_id": "none"}) == {}


def test_metrics_snapshot_all_aggregates() -> None:
    m = MetricsCollector()
    m.inc("token.used", 100.0, tags={"plugin_id": "llm"})
    m.inc("token.used", 10.0, tags={"plugin_id": "mem"})
    assert m.snapshot()["token.used"] == 110.0  # noqa: PLR2004 — 跨维度按名汇总


def test_noop_exporter_does_nothing() -> None:
    exporter = NoopExporter()
    assert exporter.emit([_event("s1")]) is None


def test_export_failure_degrades_not_blocks() -> None:
    buffered = BufferedExporter(_FailingExporter(), capacity=10)
    buffered.emit([_event("s1")])  # 不抛异常，主循环不阻塞
    assert buffered.degraded is True


def test_buffer_overflow_drops_oldest() -> None:
    buffered = BufferedExporter(_FailingExporter(), capacity=3)
    for i in range(5):
        buffered.emit([_event(str(i), ts=float(i))])
    assert buffered.dropped == 2  # noqa: PLR2004 — 超出容量按 FIFO 丢弃最旧
    assert buffered.degraded is True


def test_error_codes() -> None:
    assert ErrorCode.EXPORT_FAILED.value == "EXPORT_FAILED"
    assert ErrorCode.TELEMETRY_DEGRADED.value == "TELEMETRY_DEGRADED"
    err = TelemetryError(ErrorCode.EXPORT_FAILED, "磁盘满")
    assert str(err) == "EXPORT_FAILED: 磁盘满"
