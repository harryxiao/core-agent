# Change: 编排运行时三能力（并行扇出 / 目标监控 / 优先级调度）

## Why

change 0012 已确立 orchestration 的三层基础能力（状态机管理、子任务拆解、多 Agent 协同），但对照《Agentic Design Patterns》缺口分析，编排运行时仍缺三个关键能力：GAP-1 并行——子任务拆解虽声明「无依赖项可并行」，却无显式并发执行模型，缺 fan-out/fan-in 波次调度，同波次无依赖子任务仍被串行执行；GAP-2 目标监控——spec 无 Goal/SuccessCriteria（SMART 成功标准）与进度追踪的独立 Requirement，模块文档虽有 ProgressTracker 组件但 spec 层无定义，目标推进无法被量化校验；GAP-4 优先级——子任务无 priority 字段，多个子任务就绪时无法按优先级决定执行顺序，资源竞争缺调度依据。三能力缺失导致编排引擎「能拆解但不能并行、能执行但不能量化验收、能排序但不能按优先级调度」。

## What Changes

- 扩展 `orchestration` capability：追加 R5「并行扇出」——fan-out/fan-in 波次调度模型（同波次并行、波次间串行、受资源上限约束）
- 扩展 `orchestration` capability：追加 R6「目标监控」——Goal/SuccessCriteria（SMART）定义任务级成功标准 + ProgressTracker 进度追踪
- 扩展 `orchestration` capability：追加 R7「优先级调度」——子任务 priority 字段 + 就绪队列按优先级降序调度

## Impact

- **Affected specs**：扩展 `orchestration`（追加 R5 并行扇出、R6 目标监控、R7 优先级调度）
- **Affected docs**：`00-product/requirements.md`（1.8 任务编排追加 CORE-ORCH-R5/R6/R7 三行）、`02-modules/orchestration.md`（ProgressTracker 独立成节 + 三能力同步）、`03-interfaces/orchestration-interface.md`（priority / Goal / SuccessCriteria / 并行波次字段 / 错误码）、`01-architecture/adr.md`（追加 ADR-0030）
- **Affected code**：无（本 change 声明编排运行时能力，不涉及具体实现代码）
- **Dependencies**：复用 change 0012 的 orchestration 三层基础能力；对齐 `loop` 四阶段、`context` 信息打包、L0 EventBus 遥测
