# Design

## Context

orchestration 现有三层能力（状态机管理、子任务拆解、多 Agent 协同）已覆盖「拆解→执行→交接」主链路，但《Agentic Design Patterns》缺口分析暴露三个运行时缺陷：无显式并行执行模型（GAP-1）、无目标监控 spec 定义（GAP-2）、无优先级调度（GAP-4）。本 design 补齐三能力，与现有三层正交：状态机管「状态转移」、子任务拆解管「目标→子任务 DAG」、多 Agent 协同管「子任务→Agent 交接」，本 change 管「子任务怎么并行执行、目标怎么量化验收、就绪子任务按什么顺序执行」。

## Decisions

- **并行扇出（R5）**：将「无依赖项可并行」升级为显式波次调度模型——子任务 DAG 按依赖拓扑分层为波次（wave），同一波次内子任务无相互依赖、可并行 fan-out 到多个 loop 实例/子 Agent；波次全部完成后 fan-in 汇总校验，再推进下一波次。并行度受资源上限约束，防止过载。
- **目标监控（R6）**：引入 Goal/SuccessCriteria（SMART：具体/可度量/可达成/相关/有时限）作为任务级成功标准，子任务验收标准对齐父目标；ProgressTracker 追踪每子任务进度与整体目标推进，进度未达标触发重试/重规划（与状态机 RECOVERING 衔接）。
- **优先级调度（R7）**：子任务携带 priority 字段，就绪队列（同波次无依赖子任务）按 priority 降序调度，同优先级按入队序（FIFO）稳定执行；priority 缺省取默认值，保持向后兼容。
- **spec 扩展非新 cap**：三能力均属 orchestration 既有职责扩展，不新建 capability，改 Purpose 双向（delta 首段与正式 spec Purpose 同步扩展）。
- **架构裁决**：三项运行时能力的架构裁决记录于 ADR-0030（编号 0029+1 全局递增），proposal Impact 段同步声明。

## Risks / Trade-offs

- **并行与状态一致性**：并行执行下需支持多子任务并发状态，避免全局状态被并发写坏；依赖每子任务独立状态域/事件溯源规避。
- **SMART 标准的可判定性**：SuccessCriteria 若写成散文将不可判定，需用可判定句式（可自动校验真伪）。
- **优先级与拓扑序冲突**：priority 仅在同波次就绪子任务间生效，跨波次仍遵守依赖拓扑序，避免优先级打破依赖。

## Open Questions

- 并行度上限的具体数值（资源上限策略）留待实现阶段确定。
- priority 缺省值与动态抢占（执行中更高优先级子任务是否抢占）留待实现阶段确定。
