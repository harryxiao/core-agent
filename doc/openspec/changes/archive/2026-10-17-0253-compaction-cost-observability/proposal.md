# Change 0253 — 压实/抽取成本可观测

## Why

维护节拍与轮内压实时进程内最重的**同步**段：会话压实、中期摘要、关键事实抽取都是模型调用，
全部跑在工作线程里（`asyncio.to_thread`）。但它们此前**只有失败留痕**（`maintenance_failed`）——
成功时没有任何耗时、步骤或触发来源记录。后果：

1. **无法定位延迟来源**：一次节拍包含会话压实 / 中期摘要 / 遗忘 / 冷路径四步，迟到时不知道
   是哪一步慢；轮内压实同理（persist / memory_compact / forget）。
2. **无法评估成本与调参**：摘要器、抽取器是否值得开、维护间隔是否合理，缺少最基本的时间面。
3. **失败不可归因**：`maintenance_failed` 只带 `error`，多步并发失败时分不清哪一步抛错。

本变更只补**观测面**（P2-lite）：不改压实/抽取逻辑、不新增配置键、不引入依赖。

## What Changes

- **`DefaultLoop._maintain`**：一次实际节拍产出**一条** `maintenance` 事件，payload 含
  `elapsed_ms`（总耗时）与 `steps`（`session_compact` / `mid_summary` / `forget` / `cold_path`
  各步耗时毫秒，仅含实际执行的步骤）。
- **`DefaultLoop._compact`**：一次压实产出**一条** `compaction` 事件，payload 含
  `trigger`（`threshold` / `budget_retry`）、`elapsed_ms` 与 `steps`
  （`persist` / `memory_compact` / `forget`）。`_budget_retry` 显式传 `trigger="budget_retry"`。
- **失败归因**：两处 `maintenance_failed` payload 增 `step`（失败步骤名）；步骤失败仍不中断
  其余步骤，成本事件照常产出。
- **边界**：耗时用 `time.perf_counter()`（单调时钟）；payload **不含**条目正文、摘要文本或
  会话标识；未注入 tracer ⇒ `_trace` 空转，零事件、既有行为逐字不变。

## 影响面

- 规格：`observability` MODIFIED「全链路日志」——补成本事件条款 + 3 Scenario。
- 代码：`src/core/loop/default.py`（`_maintain` / `_compact` / `_budget_retry` 调用点）。
- 测试：新增 `tests/test_loop_cost_observability.py`（6 例）。
- 缺省行为：tracing 未注入时**无任何变化**；注入 tracing 时新增两类事件（payload 有界）。

## 不做

- 不接入 `MetricsCollector`（需给 `DefaultLoop` 增加注入面，且指标聚合与 trace 事件是两条
  消费路径；本变更只做 P2-lite 的事件面）。
- 不记录条目数 / token 数：`MemoryStore.compact` 目前不返回计数，扩展内存模块属独立课题。
- 不改维护间隔、摘要器、抽取器等任何执行逻辑。
