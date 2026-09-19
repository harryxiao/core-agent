# 模块设计：可观测性与遥测（Observability & Telemetry）

> 对应规格：`doc/openspec/specs/observability/spec.md` ｜ 接口：`doc/03-interfaces/observability-interface.md`
> 定位：**横切层**，让智能体的每一步执行都可追溯、可复盘，解决黑盒运行问题。

---

## 1. 模块定位

CORE 的每个副作用、每轮 loop、每次进化都是"可逆效应 + 结构化事件"。本模块统一采集、聚合、暴露这些事件，提供**日志、指标、链路追踪**三根支柱（三大信号）。

它同时是进化的**数据源**：Diagnoser 依赖遥测定位缺陷，Evaluator 依赖指标做留出评测。

---

## 2. 内部组成

```
TelemetryHub（横切）
├── TraceLogger      全链路日志采集：模型 IO、工具调用、耗时、返回
├── MetricsCollector 性能指标监控：完成率、token、循环次数、错误率
├── Tracer           链路追踪：单任务全流程回溯（trace_id 贯穿）
└── Exporter         导出器：JSONL / console / OpenTelemetry（可插拔）
```

---

## 3. 关键设计

### 3.1 全链路日志采集

- 记录：模型输入/输出、工具调用参数、执行耗时、返回结果、副作用（effect）。
- 结构化 JSONL，每行一个事件，带 `trace_id` + `span_id` + `ts`。
- 密钥/敏感值**脱敏**后才入日志（与 coeffect `secret` 标记联动）。

### 3.2 性能指标监控

| 指标 | 定义 |
|---|---|
| 任务完成率 | 成功完成子任务数 / 总子任务数 |
| token 消耗 | 每轮/每任务的 prompt+completion token |
| 循环次数 | 单任务消耗的 loop 轮数 |
| 错误率 | 失败 action / 总 action |

- 指标按 `trace_id` / `task_id` / `plugin_id` 聚合，供进化评估与容量分析。

### 3.3 链路追踪

- 每个任务一个 `trace_id`，贯穿 loop → 工具 → 效应 → 记忆 → 进化全链路。
- 支持**单条任务全流程回溯**：`Tracer.replay(trace_id)` 按时间序重放所有事件，快速定位失败环节。
- 与 EffectTracker 的 `audit(trace_id)` 联动，实现"执行轨迹 = 效应轨迹 + 事件轨迹"双视角。

---

## 4. 与进化的闭环

```
TelemetryHub ──事件流──► Diagnoser（定位缺陷/重复模式）
              ──指标──► Evaluator（留出集评测）
              ──日志──► 教训回写 MemoryStore（L3 降级记录）
```

---

## 5. 错误处理与可靠性

- 遥测本身故障（磁盘满/导出失败）**不得阻塞主循环**：降级为内存环形缓冲，异步落盘。
- 日志采样策略：热路径可采样（如 1/N 轮），关键事件（高危审批、回滚）不采样。

---

## 6. 关联

- 接口契约：`doc/03-interfaces/observability-interface.md`
- 规格：`doc/openspec/specs/observability/spec.md`
- 测试：`doc/04-testing/test-cases.md`（OBS 系列）
