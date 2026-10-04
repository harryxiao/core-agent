# Evolution Specification Delta

## ADDED Requirements

### Requirement: 架构级候选强制人工审批（HITL confirm gate）
系统 SHALL 按风险域区分候选的确认路径：世代化候选 SHALL 携带 `risk_level`（`high` 为架构级——
`kind="plugin"`，`low` 为技能库级——`kind="skill"`）。`risk_level="high"` 的候选 SHALL 强制走
**人工审批**：`confirm` SHALL 要求一张与候选目标一致的**已批准**权限审批单，缺失、未批准或目标
不符时 SHALL NOT 放行（fail-closed，候选保持 `pending`）；`risk_level="low"` 的候选 SHALL 仍须
**显式**人工 `confirm()`——系统 SHALL NOT 提供低风险自动结晶。

- **判定**：`risk_level` SHALL 由提案阶段按 `kind` 判定并随候选固化（不依赖调用方传入）。
- **门禁**：审批判定 SHALL 由 permission 域解释其审批单状态（域外 SHALL NOT 依赖状态字面量）。
- **可追溯**：审批单 SHALL 携带候选目标与 trace，经审批流归档可回溯。
- **拒绝不放行**：被拒/过期/超时的审批单 SHALL NOT 放行候选；`crystallize` 对未确认候选仍 SHALL
  拒绝（既有 `CANDIDATE_PENDING` 语义不变）。

#### Scenario: 架构级候选无审批单不放行
- **GIVEN** 一个 `risk_level="high"` 的候选已过验证门与留出评测
- **WHEN** 不带审批单调用 `confirm`
- **THEN** 抛结构化错误 `CONFIRM_REQUIRED`，候选 `status` 保持 `pending`，`crystallize` 拒绝

#### Scenario: 架构级候选带已批准审批单放行
- **GIVEN** 一个 `risk_level="high"` 的候选，且已有一张目标一致、经人工批准的审批单
- **WHEN** 携带该审批单调用 `confirm`
- **THEN** 候选 `status` 置 `confirmed`，`crystallize` 可发布

#### Scenario: 审批被拒不放过
- **GIVEN** 一个 `risk_level="high"` 的候选，审批单已被人工拒绝
- **WHEN** 携带该审批单调用 `confirm`
- **THEN** 抛 `CONFIRM_REQUIRED`，候选保持 `pending`

#### Scenario: 审批单目标不符不放行
- **GIVEN** 一张已批准但目标为**其他**插件的审批单
- **WHEN** 携带它确认本候选
- **THEN** 抛 `CONFIRM_REQUIRED`，候选保持 `pending`（不得跨候选复用审批）

#### Scenario: 技能级候选仍须显式人工确认
- **GIVEN** 一个 `risk_level="low"` 的候选（`kind="skill"`）
- **WHEN** 调用 `confirm`（不带审批单）
- **THEN** 候选置 `confirmed`（人工确认仍是必要条件，只是不要求权限工单），未被确认时
  `crystallize` 仍拒绝
