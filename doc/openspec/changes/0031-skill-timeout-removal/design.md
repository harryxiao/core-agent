# Design: 摘除 skills「超时与资源上限」Requirement 的边界

## Context

Phase 3 落地 skillhub 后，skills spec 的「超时与资源上限」Requirement（CORE-skills-R4）与 tool-use 能力职责重叠，且造成 spec↔interface 漂移（skills-interface 无超时/资源上限方法，SKILL_TIMEOUT 无实现落点）。

## Decisions

- **摘除而非补实现**：技能执行超时/资源上限本质是工具执行层（tool-use）的横切约束，timeout_s=30、max_output=8192 已由 tool-use 承载；skills 层专注原子技能库、版本管理与灰度/A/B、技能路由三个正交职责，不重复建模。
- **REMOVED delta 用 names-only 格式**：`## REMOVED Requirements` + `### Requirement: 超时与资源上限`（无需 Scenario 正文）。

## Non-Goals

- 不新增 tool-use 的超时/资源上限 Requirement（tool-use 已有对应能力）
- 不改动 skills-interface 方法签名（无超时/资源上限方法）
- 不调整 evolution 溶解流程

## Risks

- **低**：摘除后 skills 层失去显式超时约束；当前 skills 由 loop 调度、tool-use 承载执行，无独立执行路径，无实际影响。若未来 skills 需独立超时，在 tool-use 层统一约束。

## Open Questions

- 无
