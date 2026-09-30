# Phase 14 — 冷路径 + 长任务（进化采集 + 多 Agent 长任务编排）

> 里程碑：**M10 进化闭环**（与 Phase 15 连排，不可拆分；本 Phase 交付「采集 + 提案 dry-run」冷路径 + 长任务编排，Phase 15 交付验证门/评测/结晶）
> 位置：L4 进化冷路径（EvolutionWorker 消费 Tracer）+ L3.5 编排接线（TaskScheduler 真 DefaultLoop + checkpoint）
> 上游：Phase 13 组合根（runtime 已装配 Tracer/ToolProvider/DefaultLoop）+ Phase 4 编排（orchestration 模块）+ Phase 5 进化（evolution 四阶段引擎）
> 对应 change：无新增 openspec change（既有 evolution/orchestration/durability/observability spec 的运行时装配）

---

## 1. 范围与定位

Phase 13 打通「热路径」单 Agent 闭环（runtime → loop → LLM → tools），但存在两条**冷路径缺口**：

1. **进化采集冷路径**：运行时只**发** `TraceEvent`（`Tracer.record/end_trace`），**无人消费**。`EvolutionEngine.run_cycle` 已实现但生产代码零调用点 → 自进化「只造轮子不转」。
2. **长任务编排接线**：`TaskScheduler`/`SubtaskDecomposer`/`MultiAgentRouter`/`StateMachine` 均已实现，但 runtime 零装配 → 长任务（多子任务分解 / 多 Agent 协同 / 断点 checkpoint）无生产接线点。

本 Phase 补上这两条：

- **EvolutionWorker**：消费 `Tracer` 已完成 trace → `TraceEvent→Trace` 适配 → `EvolutionEngine.run_cycle`（诊断 → 提案，**dry-run**，不含 Phase 15 验证门/结晶）。
- **长任务编排**：runtime 装配 `TaskScheduler` + `MultiAgentRouter`（真 `DefaultLoop` 的 `AgentProfile`）+ `CheckpointManager`，长任务「decompose → 多 Agent 派发 → handoff → checkpoint」跑通。

> **命名澄清**：phase-13 §9 的「Orchestrator」是概念名，落地即已存在的 `TaskScheduler`；本 Phase **不新造 Orchestrator 类**，仅接线 + 补 checkpoint 注入。

## 2. 里程碑验收（M10 前半段）

- [x] `EvolutionWorker.maybe_run(force=True)` 消费一段真实 trace → 产出 `EvolutionOutcome`（status ∈ no_evidence/manual/pending/rejected，dry-run 不到 crystallize）
- [x] 一段「工具调用失败」的 trace 被 `Diagnoser` 归因到具体插件（`DiagnosisReport.target_plugin` 非空），`Proposer` 产出 `GenerationCandidate`
- [x] `TaskScheduler.run` 在多 Agent 下 decompose → 派发多 `DefaultLoop` → 完成多子任务（含一次 `TaskHandoff`）
- [x] 每个 wave 完成后调用 `CheckpointManager.create_checkpoint`（长任务断点可恢复）

## 3. 依赖与前置

- Phase 13（runtime 组合根已装配 `Tracer`/`DefaultLoop`/`ToolProvider`）
- Phase 4（orchestration：`SubtaskDecomposer`/`TaskScheduler`/`MultiAgentRouter`/`StateMachine`/`ProgressTracker`/`TaskHandoff`）
- Phase 5（evolution：`Collector`/`Diagnoser`/`Proposer`/`EvolutionEngine`/`EvolutionTrigger`）
- Phase 2（durability：`CheckpointManager`/`CheckpointStore`；observability：`Tracer`/`TraceEvent`）

## 4. 首步任务

1. **确认 Tracer 访问面（无需改契约）**：`DefaultLoop.run` 已返回 `LoopResult.trace_id`（loop/protocol.py:15），worker 由 entry/调用方注入 trace_id 而非轮询 `Tracer` 内部 keys，故**不改 `Tracer` 契约**。

## 5. 实现顺序

### 5.1 `src/core/evolution/worker.py`（NEW）—— 冷路径采集调度器

`EvolutionWorker`：

- 构造注入 `tracer: Tracer`、`engine: EvolutionEngine`、`trigger: EvolutionTrigger | None = None`
- `on_trace_complete(trace_id: str) -> None`：登记一条已完成 trace（热路径只登记，不阻塞）
- `maybe_run(*, force: bool = False) -> EvolutionOutcome | None`：`trigger.maybe_run` 命中或 `force` → replay 累积 trace_id → `_to_traces(list[TraceEvent])` → `engine.run_cycle(list[Trace])`
- `_to_traces(events: list[TraceEvent]) -> list[Trace]`：把同 trace_id 的 `TraceEvent` 适配为 evolution `Trace`——仅 `kind="tool_call"` 事件产出 Trace（`action` 取 tool+args，`result`/`success` 从 tool_call payload 内嵌的 result 提取）；`plugin_id` 从 tool id 归因；`effect` 为副作用记录、`metric` 无对应事件（`TraceLogger` 无 `log_metric`），均不产出 Trace

依赖约束：`evolution → observability` 合法（observability 是横切 base 模块，架构测试无禁令）。

### 5.2 `src/core/evolution/__init__.py`（MODIFY）

导出 `EvolutionWorker`（加入 `__all__`）。

### 5.3 `src/core/orchestration/` checkpoint 注入（MODIFY）

`TaskScheduler` 增加可选 `checkpoint: Callable[[str, list[SubtaskOutcome]], None] | None = None`，每个 wave 完成后调用。**用回调注入而非直接 import durability**，保持 orchestration 与 durability 解耦。

### 5.4 `src/core/runtime.py`（MODIFY）

装配（runtime 是唯一组合根，允许 import evolution/orchestration/durability）：

- `EvolutionWorker(tracer=tracer, engine=..., trigger=EvolutionTrigger())` → `Runtime.evolution`（新字段）
- `MultiAgentRouter` + 默认 `AgentProfile(loop=loop)` → `TaskScheduler(decomposer=..., router=..., state_machine=..., tracker=...)` → `Runtime.orchestrator`（新字段）
- `CheckpointManager(store=CheckpointStore())` → 以回调注入 `TaskScheduler.checkpoint`（长任务断点）

> 测试同步：`test_runtime_is_sole_composition_root` 的 `required` 集合需补 `evolution`/`orchestration`/`durability`（该集合当前只断言 runtime「至少 import 这些模块」，补齐后意图才与「组合根装配全量」一致）。

## 6. 契约对齐

| capability | 接口 § | 关键签名 |
|---|---|---|
| observability | observability-interface.md §1 | `Tracer.replay(trace_id) -> list[TraceEvent]`；`TraceEvent(trace_id, span_id, ts, kind, payload)` |
| evolution | evolution-interface.md | `EvolutionEngine.run_cycle(traces) -> EvolutionOutcome`；`EvolutionTrigger.maybe_run(traces, force)`；`Trace(action, result, success, plugin_id)` |
| orchestration | orchestration-interface.md §1/§2 | `TaskScheduler.run(task_id, goal, criteria)`；`MultiAgentRouter.register/match/handoff`；`TaskHandoff(task, ...)` |
| durability | durability-interface.md §1 | `CheckpointManager.create_checkpoint(...)` |

## 7. 门禁验收

```bash
ruff check src tests && ruff format --check src tests && pyright && pytest -q
```

- 新增 `tests/test_phase14.py`：
  - `EvolutionWorker.maybe_run(force=True)` 消费一段含 tool_call 的 trace → 产出 `EvolutionOutcome`；无证据 → `no_evidence`
  - 失败 trace 归因：`DiagnosisReport.target_plugin` 非空 + `Proposer` 产出候选
  - `TaskScheduler.run` 多 Agent（两个 AgentProfile）跑通多子任务，`checkpoint` 回调每个 wave 被调用一次
- 架构测试同步：`test_runtime_is_sole_composition_root.required` 补 `evolution`/`orchestration`/`durability`

## 8. 提交规范

`feat(phase14): 冷路径进化采集 EvolutionWorker + 长任务编排接线（M10 前半段）`

提交后更新 `README.md` §2 Phase 14 行状态列「⬜ 待开始」→「✅ 完成」。
