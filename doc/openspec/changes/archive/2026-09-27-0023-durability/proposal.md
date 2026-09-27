# Change: 新增 durability 持久化 capability（检查点快照 / 崩溃恢复 / 时间旅行 / 保留策略）

## Why

上轮与 CrewAI / Microsoft Agent Framework（MAF）架构对比（retrospective.md）发现：Core-Agent 缺少 durability 能力——grep 全 doc/ 英文 checkpoint/time-travel/durable 与中文「状态持久化/崩溃恢复」均 0 命中（来源：exploration_findings.md，2026-09-25）。对照主流 Agent 框架（CrewAI 任务状态持久化、MAF checkpointing 快照 + time-travel 调试回放），Core-Agent 需要一条独立的 durability capability 描述「执行态如何保存、恢复、回滚」：

- 现有 `orchestration`「断点续跑」只覆盖任务级挂起/恢复/取消，`tool-use`「时间旅行回滚」只覆盖副作用级 EffectId undo 栈，两者都未统一到执行态级（执行上下文、任务状态、中间结果、记忆、会话状态）的持久化与恢复。
- `loop` 四阶段（perceive/decide/act/observe）无执行态持久化/恢复机制；`data-model.md` 已有「4. 待补定义实体」预留点。

## What Changes

- **durability**：新增独立 capability，4 条 Requirement（检查点快照、崩溃恢复、时间旅行、生命周期保留策略），9 条 Scenario，与 orchestration/tool-use 正交。
- **挂载点标注**：orchestration「断点续跑」与 tool-use「时间旅行回滚」加交叉引用注释指向 durability（不改原 Requirement 正文，仅加引用）。
- **03-interfaces**：新建 `durability-interface.md`，固化 Checkpoint/Snapshot/Restore/Rollback 实体签名。
- **02-modules**：新建 `durability.md` 模块实现文档（架构/存储后端/恢复流程/与 loop 挂接）。
- **data-model.md**：补 Checkpoint/Snapshot/RestoreHandle/RetentionPolicy 实体（落「4. 待补定义实体」）。
- **adr.md**：追加 ADR-0032（durability 作为独立 capability 的边界与执行态抽象决策）。
- **requirements.md**：补 1.22 durability 条目 + CORE-DUR-Rn 表格行；同步派生数字口径（21→22）。

## Impact

- **Affected specs**：`durability`（新增，4 Requirement）；`orchestration`、`tool-use`（加挂载点交叉引用注释，不改 Requirement 正文）
- **Affected docs**：`02-modules/durability.md`（新建）、`03-interfaces/durability-interface.md`（新建）、`00-product/requirements.md`（+1.22 + CORE-DUR-Rn 表格行）、`00-product/design-completeness-eval.md`（派生数字 21→22）、`00-product/design-completeness-audit.md`（派生数字 21→22、17→18）、`00-product/retrospective.md`（派生数字 21→22、16→17、19→20、31→32）、`04-testing/test-strategy.md`（覆盖矩阵 21→22）、`01-architecture/adr.md`（+ADR-0032）、`01-architecture/architecture-overview.md`（横切列表 + 核心组件表 + 功能域）、`01-architecture/data-model.md`（+Checkpoint/Snapshot/RestoreHandle/RetentionPolicy）、`README.md`（核心组件表 +durability 行）
- **Affected code**：无（规格与设计文档落地；工程实现依赖后续任务）
- **Dependencies**：复用 orchestration「断点续跑」、tool-use「时间旅行回滚」（EffectId undo 栈，不新建撤销机制）；ADR 编号=当前最大+1（0032）；派生数字口径 21→22 全局同步
