"""observability 生产导出器装配（change 0089 / Phase 20 C4）。

组合根（`build_runtime`）在未注入 tracer 时 SHALL 装配**生产导出面**：结构化事件以 JSONL 追加
落 `$CORE_STATE_DIR/traces.jsonl`（缺省 `~/.core/state`），且经**缓冲 / 退避重试导出器**包装
（导出失败降级为内存缓冲，绝不抛给主循环）。显式注入的 tracer SHALL 优先。
"""

from __future__ import annotations

from core.configuration import ConfigManager
from core.observability import BufferedExporter, JSONLExporter, TraceEvent, Tracer
from core.runtime import build_runtime


def _write_config(tmp_path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n",
        encoding="utf-8",
    )
    return str(cfg)


def _build(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))


def _event(trace_id: str, span_id: str) -> TraceEvent:
    return TraceEvent(
        trace_id=trace_id, span_id=span_id, ts=0.0, kind="tool_call", payload={"ok": True}
    )


def test_default_tracer_writes_jsonl_to_state_dir(monkeypatch, tmp_path) -> None:
    """缺省导出面：`end_trace` 后事件落 `$CORE_STATE_DIR/traces.jsonl`（conftest 已隔离）。"""
    runtime = _build(monkeypatch, tmp_path)
    trace_id = runtime.tracer.start_trace("t1")
    runtime.tracer.record(_event(trace_id, "s1"))
    runtime.tracer.end_trace(trace_id)

    path = tmp_path / "state" / "traces.jsonl"
    assert path.exists(), "缺省导出器应把事件落 $CORE_STATE_DIR/traces.jsonl"
    assert '"span_id": "s1"' in path.read_text(encoding="utf-8")


def test_default_exporter_is_buffered_jsonl(monkeypatch, tmp_path) -> None:
    """装配的导出面经缓冲包装 ⇒ 落盘失败降级为内存缓冲，绝不抛进主循环。"""
    runtime = _build(monkeypatch, tmp_path)
    exporter = runtime.tracer._exporter  # 装配断言（同 test_phase13 私有属性风格）

    assert isinstance(exporter, BufferedExporter), "缺省导出面须经缓冲/退避重试包装"
    assert isinstance(exporter._inner, JSONLExporter)


def test_jsonl_exporter_creates_parent_dir(tmp_path) -> None:
    """导出目标父目录不存在时自建（镜像 FileBackend；否则事件静默丢弃）。"""
    target = tmp_path / "deep" / "nested" / "traces.jsonl"
    JSONLExporter(target).emit([_event("t2", "s2")])
    assert target.exists()


def test_injected_tracer_takes_precedence(monkeypatch, tmp_path) -> None:
    """显式注入的 tracer 优先，不被缺省生产导出器覆盖。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    injected = Tracer()
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)), tracer=injected)

    assert runtime.tracer is injected
