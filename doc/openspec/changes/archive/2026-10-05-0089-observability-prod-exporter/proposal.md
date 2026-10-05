# 0089 — observability 生产导出器装配（Phase 20 C4）

## 为什么

账本 `coding-plan/phase-20.md` §1 C4：**可观测性的导出器在生产从未装配** —— 组合根 `build_runtime` 在调用方
未注入 tracer 时 `Tracer()` **不传 exporter**（`runtime.py:224`），`Tracer` 缺省 `NoopExporter`（`tracer.py:24-26`）
⇒ **生产环境零导出**。而 observability 规格 Requirement「全链路日志」明文要求「系统 SHALL 记录…结构化」，
且 Requirement「遥测缓冲与导出重试」要求导出失败降级不阻塞主循环。

导出器实现（`JSONLExporter` / `ConsoleExporter` / `BufferedExporter`）**全部已实现且已测**，唯一缺的是
**组合根装配** —— 抽象的最后一个未接线接缝（与 Phase 19 反复记的「实现已落地、缺生产触达点」同型）。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/runtime.py` | 新增 `_trace_path()`（`$CORE_STATE_DIR/traces.jsonl`，同既有 `_memory_path` 约定）；`:224` 未注入时改装配 `Tracer(exporter=BufferedExporter(JSONLExporter(_trace_path())))` |
| `doc/openspec/specs/observability/spec.md` | MODIFIED「全链路日志」：补组合根装配生产导出器 + 注入优先；补 2 场景 |
| `doc/03-interfaces/observability-interface.md` | §5 补「生产装配」口径（缺省导出器 = JSONL 落 state dir，经缓冲包装） |
| `doc/02-modules/observability.md` | §3.1 / §5 按实际接线订正（此前「Phase 0 缺省 no-op」） |
| `doc/01-architecture/adr.md` | ADR-0084 + 映射表行 |
| `doc/04-testing/test-cases.md` | TC-OBS-05（组合根装配落盘） |
| `tests/test_observability_wiring.py` | 新：组合根装配断言（落盘 + 缓冲包装 + 注入优先） |

## 决策

- **缺省 = `BufferedExporter(JSONLExporter(...))`**：JSONL 满足「结构化记录」，外层缓冲满足「导出失败不阻塞
  主循环」（`BufferedExporter.emit` 内已 `except` 降级，绝不抛给 loop）。二者都是规格**明文要求**，非投机。
- **落 `$CORE_STATE_DIR/traces.jsonl`**：复用既有状态目录约定（checkpoints / memory / pets / mcp-endpoints 同源），
  env 覆盖便于测试隔离（`conftest` autouse 已把 `CORE_STATE_DIR` 指到 tmp）。
- **注入优先**：`tracer=` 形参已存在（SUT 与宿主替换导出面的接缝），保持不变 —— 仅填**缺省**分支。
- **不加配置开关、不加 `Runtime` 字段**：规格未要求可配导出面；`Runtime` 字段集被多测试隐式断言，不动。
- **不引入 OTel/Prometheus**：那些是「指标导出协议」的凭证/依赖半（第三方 SDK），归 Phase 19 §5；本变更只做
  **零依赖**的日志导出装配。

## 明确不做

- **不做 OTel / Prometheus 导出器**（`Requirement: 指标导出协议`）：需第三方 SDK（依赖红线外 + 网络），另案。
- **不做告警规则**（`Requirement: 告警规则`）：本变更只补「日志导出装配」这一处缺口，不扩面。
- **不做指标采集的装配**：`MetricsCollector` 是否入组合根是另一项，本变更不夹带（保持 surgical）。
