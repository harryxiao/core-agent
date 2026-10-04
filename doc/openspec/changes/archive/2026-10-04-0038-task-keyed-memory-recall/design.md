# Design: 上下文按任务召回记忆

## 决策 1：检索归属 —— ContextEngine.assemble（而非 Loop.perceive）

**依据**：`architecture-overview.md:117` 数据流 `Loop.perceive ─► ContextEngine.assemble
─► MemoryStore.retrieve(注入)`；`:91` MemoryStore=L2「存储 + 检索」、`:93`
ContextEngine=L3「装配」。检索由 L3 装配器发起，与 L2 存储解耦，perceive 不持有检索职责。

**取舍**：
- **A（perceive 检索）**：把 retrieve 挪进 loop → 与数据流冲突，且需改 context spec，loop 越层持有 L2 检索。
- **B（装配器检索，本变更）**：retrieve 留在 ContextEngine，仅修正 query；perceive 撤越权检索 →
  代码向架构图**收敛**，无 spec 越层。

## 决策 2：检索 query —— task（而非 stage）

`stage` 在唯一调用点恒为 `"reason"`，作 query 只会召回到「与常量字符串相似」的噪音。
任务目标是本轮最贴切的检索信号，故 query = `task`。

**兼容性**：`stage` 字段保留（仍作装配阶段标注、参与 token 计数），仅不再作检索 query；
`ContextPack.stage` 契约不变。

## 决策 3：perceive 撤检索后 `LoopContext.memory` 的处理

`ctx.memory` 无消费方（全仓 grep 确认）。本变更**不删字段**（保持机械可逆、变更最小），
仅停止填充 → 字段成为占位。字段废弃化登记为 Phase 18 遗留 A1，避免本变更越界动 loop 契约。

## 风险与缓解

- 既有测试若断言「stage 命中事实」→ 同步为 task-keyed（tasks 2.1 覆盖）。
- 预算：检索命中的事实规模由 query 决定，仍经 `BudgetManager` 截断至 budget，token 上界不变。
