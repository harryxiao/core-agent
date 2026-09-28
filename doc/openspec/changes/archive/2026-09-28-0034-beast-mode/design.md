# Design: beast-mode 神兽召唤层（召唤=handoff / 并发多兽 / 异步并发执行+自动回归）

## Context

pet-mode（Phase 8）落地「后台重复简单任务」（信息收集/闲逛探索），但缺少「前台重大任务」的对偶：用户有重大任务（架构设计/性能攻坚/安全审计/测试生成）时，需要一个独立子 Agent 前台接管、异步并发执行并自动回归。orchestration 已有 `MultiAgentRouter`（register/match/handoff）+ `AgentProfile`（agent_id/capabilities/loop）+ `TaskHandoff`（task/context_pack/acceptance/deadline/priority）完整交接基础设施；skills 已有全局 `SkillLibrary`（register/param_schema 校验）+ `SkillRouter`（match 打分，零运行时消费方）；pet 已有 `PetSession` 三入口范式可平移。

## Decisions

1. **召唤 = handoff**（铁律 1）：神兽是内置预定义 `AgentProfile`，召唤即 `MultiAgentRouter.handoff(beast_id, TaskHandoff(...))`，复用编排层既有交接语义，不另造第二真源。
2. **并发多兽**（A3）：`BeastSession` 维护 `dict[agent_id, BeastSession]` 多实例，可同时显形多兽并行执行；同兽重复召唤先拒绝或先回归（兽间并行、兽内串行）。
3. **异步并发执行 + 自动回归**（D3）：召唤异步并发执行（`handoff` 经 `loop.arun` 非阻塞，多兽并行互不阻塞，契合「前台重大任务」）；任务完成据 `LoopResult.failed` 判定成败自动回归，手动复位（`/recall <beast>`/`recall <beast>` CLI/NL）按 beast_id 复位，异步执行下无「中断在岗兽」窗口。
4. **独立子 Agent + 共享能力集**（D2）：神兽 `AgentProfile.loop` 为独立 `LoopPlugin` 实例 → 独立记忆 namespace（`MemoryEntry.source = beast.<agent_id>`）+ 独立上下文（`DynamicAssembler.build()` 按任务阶段装配）；运行时能力分两层：L1 工具共享全局 `ToolProvider`（loop 原生消费，通用能力真实可用）+ L3 技能（神通 `beast.*`）注册进全局 `SkillLibrary`（注册/共享实例可验证，loop→skill 运行时调用 deferred）。
5. **契约小改不重建**：`LoopResult.failed`（增量字段，默认 False）+ `handoff` 异步执行（`loop.run`→`loop.arun`）并返回完整 `LoopResult`（返回值从 `trace_id` 升级为完整对象，`trace_id` 字段保留），不重建编排层。
6. **复用 pet 六模块骨架**：以 `src/core/pet/` 为模板平移出 `src/core/beast/`（registry/session/activator/skills），保持相同分层粒度与三入口结构。

## Risks

- **契约改动波及既有 handoff 调用方**：`handoff` 返回值类型变更（str → LoopResult）且同步改异步（`loop.run`→`loop.arun`），实现期须保留 `trace_id` 字段兼容既有调用方、既有同步调用方适配异步。
- **神通运行时调用缺桥接**：L3 技能 loop→skill 调用 deferred，神兽 loop 短期只拿 L1 工具 + 技能元数据，避免承诺未实现能力（tasks.md 显式标注 deferred）。
- **`beast.<拼音>.<skill>` 3 段命名与 `_domain()` 索引语义冲突**：`_domain()` 取 `parts[1]`=拼音 → 20 兽各成一个拼音 domain，`list_by_domain("beast")` 恒空；专属路由不依赖该索引，由 `BeastSession` 按 agent_id 前缀过滤候选。

## Open Questions

- 神兽 `AgentProfile.loop` 的独立 `LoopPlugin` 实例化方式（每兽一实例 vs 模板克隆）待实现期确定。
- `handoff` 同步返回 `trace_id` 改异步返回完整 `LoopResult`（str → LoopResult + run→arun）对既有调用方的迁移策略（渐进 vs 一次性）待实现期确定。
- 神通 `beast.*` Skill 的 `instructions` 内容（山海经神兽人格 prompt）待实现期拟定。
