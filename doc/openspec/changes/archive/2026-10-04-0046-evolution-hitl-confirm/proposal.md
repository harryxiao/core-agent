# Proposal: 架构级候选强制人工审批（evolution HITL confirm gate）

## Why

Phase 18 #9（维度2 架构级进化的「人工审核必审」收口）。

1. **`confirm` 是裸 setter**：`EvolutionEngine.confirm(candidate)` 只做 `candidate.status =
   "confirmed"`（engine.py:104-106）——任何调用方一句话就把候选放行，**与权限审批流没有任何
   联动**。而 evolution spec「结晶为技能/SOP」的 Scenario「候选待人工确认」明确要求
   「进入评审队列，通过后入 skills 库（**与权限审批流联动**）」——该联动在生产不存在。
2. **`risk_level` 不存在**：`GenerationCandidate` 只有 `kind`（skill/plugin），没有风险域标注；
   「维度1 技能库（可自动）vs 维度2 架构（必审）」的判据无处承载（phase-18 §4 第 8 条），
   架构级候选与技能候选在确认路径上**完全没有区别**。
3. **权限侧能力已备、无调用者**：`ApprovalWorkflow`（create → ask → approve/reject/edit_plan
   + 归档）已落地，但**状态词表 `"approved"` 是模块私有**（`approval.py:19-24`），域外无法
   判定一张单据是否已批准 → 「联动」无处下手。

## What Changes

- **ADDED Requirement: 架构级候选强制人工审批（HITL confirm gate）**——
  `GenerationCandidate` SHALL 携带 `risk_level`（提案阶段判定：`kind="plugin"` → `high`，
  `kind="skill"` → `low`）；`risk_level="high"` 的候选 `confirm` SHALL 要求一张**已批准**的
  权限审批单且目标一致，缺失/未批准/目标不符 SHALL NOT 放行（fail-closed，候选保持
  `pending`）；`risk_level="low"` 的候选 SHALL 仍须**显式**人工 `confirm()`（不引入低风险
  自动结晶）。
- `GenerationCandidate` 增 `risk_level: Literal["low", "high"] = "low"`（默认值向后兼容）。
- `Proposer.propose` 按 `kind` 判定 `risk_level`。
- **permission 域新增判定谓词** `is_approved(ticket) -> bool`（解释本域状态词表，含
  `result.approved` 复核）并导出——供域外做 HITL 门判定，不泄漏 `"approved"` 字面量。
- `EvolutionEngine.confirm(candidate, *, approval: ApprovalTicket | None = None)`：
  `high` → 校验审批单（存在 + 已批准 + `request.target == candidate.target_plugin`）；
  `low` → 忽略 `approval`，行为同今天。
- 新增错误码 `EvolutionErrorCode.CONFIRM_REQUIRED`。

## Non-goals

- **审批单的创建/推进**：engine 不建单、不阻塞等待人工——单据生命周期属 permission
  （`ApprovalWorkflow`）与交互端（`ApprovalChannel` / UI / IM）；engine 只做**门禁校验**。
- **低风险自动结晶**：明确不引入（phase-18 §4 第 8 条）；`low` 仍须人工 `confirm()`。
- **观察期自动溶解**：#10（下一个 change）。
- **审批结果回写记忆/世代账本**：可追溯性由审批单自身的归档（`list_archived` + `request.trace_id`
  / `target`）承载，本次不新增持久化字段。

## Impact

- 规格：`evolution/spec.md`（+1 Requirement，5 Scenario）。
- 代码：`src/core/evolution/models.py`（`risk_level`）、`proposer.py`（判定）、
  `engine.py`（`confirm` 门禁）、`errors.py`（+1 错误码）；`src/core/permission/approval.py`
  （`is_approved` 谓词）+ `permission/__init__.py` 导出。
- 契约：`doc/03-interfaces/evolution-interface.md`（`confirm` 签名 + `risk_level` 字段 +
  错误码）、`doc/03-interfaces/permission-interface.md`（`is_approved`）、ADR-0051。
- 兼容性：`GenerationCandidate` 新字段有默认值；`confirm(candidate)` 对 `low` 候选行为不变
  ——既有测试与调用方（`test_evolution.py` 默认 `Proposer(kind="skill")`）零改动。

## Risks

- **门禁形同虚设**（调用方自造一张 `status="approved"` 的单据）：单据由 permission 域构造，
  状态迁移只经 `ApprovalWorkflow._resolve`；本次额外校验 `request.target` 与候选一致，挡住
  「拿别的单子解锁」。进程内信任边界与既有 `approver`/`ApprovalChannel` 一致（如实记录）。
- **强制审批卡住自动流程**：`high` 只覆盖 `kind="plugin"`（架构级），维度1 技能库链路
  （SOP 提炼 → `SkillLibrary`）不经 evolution engine，不受影响。
