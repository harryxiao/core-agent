# Change: 神兽召唤层——beast-mode / summon（前台重大任务，pet-mode 的对偶）

## Why

pet-mode（Phase 8）只覆盖「后台重复简单任务」（信息收集/闲逛探索），缺少「前台重大任务」的对偶能力：当用户有重大任务（架构设计、性能攻坚、安全审计、测试生成等）时，需要一个独立子 Agent 前台接管、异步并发执行并自动回归。为此新增 beast-mode：20 个预定义山海经神兽，各持独有神通（L3 Skill），并直接复用主 Agent 通用能力（L1 工具 + L3 技能库）执行重大任务。

三条接线缺口驱动本次变更：
1. **无 beast 规格**：`openspec/specs/` 无 beast/summon，神兽召唤无行为规格可依。
2. **`LoopResult` 无成败信号**：`loop/protocol.py` 仅 `reply + trace_id`，神兽 loop 完成后编排层无法判定成败 → 自动回归缺信号。
3. **`handoff` 丢弃完整结果**：`MultiAgentRouter.handoff()` 同步执行后仅返回 `trace_id`（router.py:50-51），召唤方拿不到完整 `LoopResult` → 无法据 `failed` 驱动回归。

## What Changes

- **beast-mode**（新增 capability，**CORE-BEAST-R1~R8 ADDED**）：20 山海经神兽注册表（只读）+ `BeastSession` 多实例四态状态机 + 召唤/回归闭环 + 三入口激活。
- **loop**（**CORE-LOOP-R1 MODIFIED**）：`LoopResult` 补 `failed` 成败信号（目标未达成/异常终止/预算耗尽为 True）。
- **orchestration**（**CORE-ORCH-R3 MODIFIED**）：`MultiAgentRouter.handoff` 异步执行子 Agent（`loop.run`→`loop.arun`）并返回完整 `LoopResult`（含 `failed`），不再只返回 `trace_id`。

## Impact

- **Affected specs**：`beast-mode/spec.md`（ADDED，8 条 Requirement）、`loop/spec.md`（MODIFIED 执行循环）、`orchestration/spec.md`（MODIFIED 多 Agent 协同）
- **Affected docs**：`03-interfaces/beast-mode-interface.md`（新增，实现期）、`03-interfaces/cli-ops-interface.md` + `cli-contract-baseline.md`（summon/recall 动词 30→32，实现期）、`00-product/requirements.md`（新增 1.28 beast-mode，CORE-BEAST-R1~R8）
- **Affected code**：`src/core/beast/`（六模块，复用 pet 骨架）、`loop/protocol.py`（LoopResult.failed）、`orchestration/router.py`（handoff 异步执行并返回完整结果）、`skills/library.py`（20 神通注册）——实现期（M7）
- **Dependencies**：`orchestration`（MultiAgentRouter/AgentProfile/TaskHandoff）、`skills`（SkillLibrary）、`pet`（三入口范式）、`context`/`memory`（独立命名空间）；无新三方依赖

## Non-goals

- 神通（`beast.*` Skill）的 **loop→skill 运行时调用桥接** 本变更不落地（loop 仍只消费 `ToolProvider`；`SkillRouter` 零消费方维持），仅做注册 + 专属路由语义。
- pet.md 式的**用户自定义神兽**不落地——20 神兽内置只读，用户自定义留待后续。

## 风险

- **契约小改波及编排层**：`LoopResult.failed` + `handoff` 返回完整结果改动 loop/orchestration 契约，但均为增量字段/返回值扩展（`failed` 新增默认 False；`handoff` 返回值从 `trace_id` 升级为完整对象 + 同步改异步 `loop.run`→`loop.arun`，`LoopResult.trace_id` 字段保留，既有调用方兼容）。
- **神兽能力复用边界**：L3 技能运行时调用 deferred，神兽 loop 短期内只拿到 L1 工具 + 已注册技能元数据，通用技能的实际执行需等桥接落地，避免承诺未实现能力（tasks.md 显式标注 deferred）。
- **20 神通 Skill 命名空间**：`beast.<拼音>.<skill>` 为 3 段 id，`_domain()` 取 `parts[1]` 会把 20 兽拆成 20 个拼音 domain（`list_by_domain("beast")` 恒空）；专属路由不依赖 `_domain()` 索引，由 `BeastSession` 按 agent_id 前缀过滤候选，避免误导性索引语义。
