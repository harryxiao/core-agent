# 接口设计：可观测性（Observability Interface）

> 模块：`02-modules/observability.md` ｜ 规格：`openspec/specs/observability/spec.md`

---

## 1. 事件模型

```python
@dataclass
class TraceEvent:
    trace_id: str               # 单任务全链路 id
    span_id: str                # 单步 span id
    ts: float
    kind: str                   # "model_io" | "tool_call" | "effect" | "metric"
    payload: dict               # 脱敏后的结构化内容
```

---

## 2. TraceLogger 接口

```python
class TraceLogger:
    def log_model_io(self, trace_id: str, prompt: str, completion: str, latency_ms: float) -> None:
        """记录模型输入/输出（密钥脱敏）。"""

    def log_tool_call(self, trace_id: str, tool: str, args: dict, result: dict, latency_ms: float) -> None:
        """记录工具调用参数/结果/耗时。"""

    def log_effect(self, trace_id: str, effect: dict) -> None:
        """关联副作用记录。"""
```

---

## 3. MetricsCollector 接口

```python
class MetricsCollector:
    def inc(self, name: str, value: float = 1.0, *, tags: dict) -> None:
        """累计指标（如 task_completed / token_used / error_count）。"""

    def gauge(self, name: str, value: float, *, tags: dict) -> None:
        """瞬时指标（如 loop_rounds / active_tasks）。"""

    def snapshot(self, *, tags: dict) -> dict[str, float]:
        """按 tags 聚合返回指标快照。"""
```

核心指标名（约定）：

| 指标 | 说明 |
|---|---|
| `task.completion_rate` | 子任务完成率 |
| `token.used` | token 消耗 |
| `loop.rounds` | 循环次数 |
| `action.error_rate` | 错误率 |

---

## 4. Tracer 接口

```python
class Tracer:
    def start_trace(self, task_id: str) -> str:
        """开启一条 trace，返回 trace_id。"""

    def end_trace(self, trace_id: str) -> None: ...

    def replay(self, trace_id: str) -> list[TraceEvent]:
        """按时间序重放全链路事件，支持单任务回溯。"""
```

---

## 5. Exporter 接口

```python
class Exporter(Protocol):
    def emit(self, events: list[TraceEvent]) -> None: ...

# 内置导出器：JSONLExporter / ConsoleExporter / NoopExporter / BufferedExporter（可插拔）
# OTel / Prometheus 导出器经同一协议接入（需第三方 SDK，未接）。
```

**生产装配**（change 0089）：组合根 `build_runtime` 在未注入 tracer 时装配
`Tracer(exporter=BufferedExporter(JSONLExporter($CORE_STATE_DIR/traces.jsonl)))` —— 结构化 JSONL 落盘 +
缓冲 / 退避重试包装（导出失败降级为内存缓冲，不阻塞主循环）；`JSONLExporter` 自建父目录；显式注入的 tracer 优先。

---

## 6. 错误码

| 错误码 | 含义 |
|---|---|
| `TELEMETRY_DEGRADED` | 遥测降级（内存缓冲，不阻塞主循环） |
| `EXPORT_FAILED` | 导出失败（异步重试） |

---

## 7. 关联

- 模块：`02-modules/observability.md`
- 规格：`openspec/specs/observability/spec.md`
