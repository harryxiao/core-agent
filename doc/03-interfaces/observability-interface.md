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
                                # | "maintenance" | "compaction" | 模块失败留痕
    payload: dict               # 脱敏后的结构化内容
    module_id: str | None = None  # 模块归因：产生该事件的架构模块 id（如 "loop.default"），缺省未归因
```

---

## 2. TraceLogger 接口

```python
class TraceLogger:
    def log_model_io(self, trace_id: str, prompt: str, completion: str, latency_ms: float) -> None:
        """记录模型输入/输出（密钥脱敏）。"""

    def log_tool_call(self, trace_id: str, tool: str, args: dict | str, result: dict, latency_ms: float) -> None:
        """记录工具调用参数/结果/耗时（``args`` 允许为节选字符串 ⇒ 事件面有界）。"""

    def log_effect(self, trace_id: str, effect: dict) -> None:
        """关联副作用记录。"""
```

**成本事件（change 0253 / ADR-0243）**：执行循环直接 `record` 两类事件 —— `maintenance`
（每实际维护节拍一条，payload `elapsed_ms` + `steps`：`session_compact` / `mid_summary` /
`forget` / `cold_path`）与 `compaction`（每压实一条，payload `trigger`（`threshold` /
`budget_retry`）+ `elapsed_ms` + `steps`：`persist` / `memory_compact` / `forget`）。步骤失败
另记 `maintenance_failed`（`step` + `error`），其余步骤继续。耗时用单调时钟；payload **不含**
条目正文、摘要文本或会话标识；未注入 tracer ⇒ 零事件。

**`tool_call` 的生产方（change 0107）**：`log_tool_call` 的**唯一生产调用方**是执行循环
（`DefaultLoop._log_tool_call`）——`astream` 在**非终止动作**完成后、与 `action_completed` **同点**
产出（载荷 `tool` = 工具 id / `args` / `result = {"ok", "output"}` / `latency_ms`；参数与输出复用
节选函数 ⇒ 与事件载荷**同源同界**）。判据与 `action_completed` 一致（终止动作不产）；
**未注入 `tracer` 不产**。该通道供 `EvolutionWorker._to_traces` 按工具 id 归因（`task_type="tool_use"`）。

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
    """只保**在途**（未封口）链路的事件 ⇒ 内存占用不随已封口 trace 数增长。"""

    def start_trace(self, task_id: str) -> str:
        """开启一条 trace，返回 trace_id。"""

    def end_trace(self, trace_id: str) -> None:
        """**封口**：事件交付导出器（落盘为真源）并从内存移除。"""

    def replay(self, trace_id: str) -> list[TraceEvent]:
        """按时间序重放**在途**链路事件，支持执行中定位失败环节。

        已完成（已封口）链路的回溯以**落盘遥测**（导出器产出）为真源。
        """
```

**责任分区（change 0103）**：生命周期由**驱动方**（`loop` 开轮 `start_trace` / 收尾 `end_trace`）
持有；**已完成**链路的留存归**消费者**——需要在本轮事件上做事的一方（如 evolution 冷路径回调）
须在**封口之前**取快照（`EvolutionWorker.on_trace_complete` 即 `replay` 快照）。故 `loop` 的收尾顺序
SHALL 为「记录遥测 → trace 完成回调 → `end_trace` 封口」，反序会让回调读到空链路（静默失效）。

---

## 5. Exporter 接口

```python
class Exporter(Protocol):
    def emit(self, events: list[TraceEvent]) -> None: ...

# 内置导出器：JSONLExporter / ConsoleExporter / NoopExporter / BufferedExporter（可插拔）
# OTel / Prometheus 导出器经同一协议接入（需第三方 SDK，未接）。
```

协议面**只有 `emit`**（无独立 `flush`）：`BufferedExporter.emit` 内部即 flush（失败降级为缓冲），
`JSONLExporter.emit` 追加落盘并自建父目录。⇒ `Tracer.end_trace` 只调 `exporter.emit(events)`，
不需要（也无从）单独 flush。

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
