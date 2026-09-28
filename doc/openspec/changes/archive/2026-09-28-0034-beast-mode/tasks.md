# Tasks

## 1. 契约层 — beast-mode spec delta（P0，本 Phase）

- [x] 1.1 写 8 Requirement（Beast Registry / Beast Session Lifecycle / Summon via Handoff / Independent Sub-Agent with Shared Capability / Innate Skills and Dedicated Routing / Async Concurrent Execution and Auto-Recall / Manual Recall / Three-Entry Activation）
- [x] 1.2 proposal What Changes ADDED bullet 标题与 delta Requirement 逐字一致
- [x] 1.3 delta 与 specs/beast-mode/spec.md 逐字一致（archive 后）

## 2. loop/orchestration 契约 delta（P0，本 Phase）

- [x] 2.1 MODIFIED loop「执行循环」：LoopResult 补 failed 成败信号
- [x] 2.2 MODIFIED orchestration「多 Agent 协同」：handoff 异步执行（loop.arun）并返回完整 LoopResult

## 3. 需求编号（P0，本 Phase）

- [x] 3.1 requirements.md 新增 1.28 beast-mode（CORE-BEAST-R1~R8）

## 4. 验证（P0）

- [x] 4.1 openspec validate --all 全绿


## 5. beast-mode 8 Requirement 实现任务（代码本 Phase 落地）

- [x] 5.1 Beast Registry（二十神兽注册表）：内置 20 山海经神兽只读注册表（agent_id=beast.<拼音>，称号/领域/独有神通/能力标签），运行期无写入口。依赖：CORE-BEAST-R1。验收：20 兽唯一标识、别名解析（agent_id/称号/拼音）、注册表不可增改
- [x] 5.2 Beast Session Lifecycle（四态会话）：DORMANT→MANIFEST→ACTIVE→RECALLED 四态状态机 + dict[agent_id, BeastSession] 多实例（兽间并行、兽内串行）。依赖：CORE-BEAST-R2。验收：多兽同时显形并行、同兽重复召唤拒绝、非法转移拒绝
- [x] 5.3 Summon via Handoff（召唤=交接）：召唤实现为 MultiAgentRouter.handoff(beast_id, TaskHandoff(...))，神兽即内置 AgentProfile，复用编排层交接语义。依赖：CORE-BEAST-R3。验收：召唤经 handoff 交接、无匹配神兽返回 NO_AGENT_MATCH
- [x] 5.4 Independent Sub-Agent with Shared Capability（独立子 Agent + 共享能力）：独立 LoopPlugin 实例 + 独立记忆命名空间（source=beast.<agent_id> 落 L2，与主 Agent source=loop 隔离）+ 神通注册进全局 SkillLibrary。依赖：CORE-BEAST-R4。验收：记忆分区隔离、SkillLibrary 注册共享可验证（loop→skill 运行时调用 deferred；L1 ToolProvider 共享经注入 loop 实现，BeastManager 默认独立 DefaultLoop 实例）
- [x] 5.5 Innate Skills and Dedicated Routing（神通注册 + 专属路由）：20 神通以 Skill 契约（skill_id/preconditions/param_schema）注册进全局 SkillLibrary，命名空间 beast.<拼音>。依赖：CORE-BEAST-R5。验收：20 神通注册可验证；专属路由定语义 + 单测断言（runtime 调用 deferred）
- [x] 5.6 Async Concurrent Execution and Auto-Recall（异步并发 + 自动回归）：handoff 经 loop.arun 异步执行返回完整 LoopResult，多兽并行互不阻塞；据 LoopResult.failed 判定成败自动迁 RECALLED。依赖：CORE-BEAST-R6。验收：异步返回完整 LoopResult、failed 判定后自动回归 RECALLED
- [x] 5.7 Manual Recall（手动复位）：/recall、recall CLI、NL「召回」按 beast_id 复位至 RECALLED，他兽不受影响，复位后可再次召唤。依赖：CORE-BEAST-R7。验收：目标兽复位、他兽不受影响、可再次召唤
- [x] 5.8 Three-Entry Activation（三入口）：/summon 斜杠 + summon <beast> [task] CLI + WebUI NL 三入口落到同一 BeastSession 生命周期（BeastActivator 三方法 + 三复位方法）。依赖：CORE-BEAST-R8。验收：三入口同源（真实 list_tools / CommandGroup / IMGateway 接线 deferred 至 Phase 9 入口层）
