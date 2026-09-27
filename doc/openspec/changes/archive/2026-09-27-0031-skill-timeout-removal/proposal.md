# Change: 摘除 skills「超时与资源上限」Requirement

## Why

Phase 3 落地 skillhub（0028）后发现 skills 的「超时与资源上限」Requirement（CORE-skills-R4）与 tool-use 能力职责重叠：技能执行超时/资源上限本质是工具执行层的横切约束，`timeout_s=30`、`max_output=8192` 等参数已由 tool-use 承载。skills 层专注「原子技能库、版本管理与灰度/A/B、技能路由」三个正交职责，不应重复建模执行层约束。

该 Requirement 还造成 spec↔interface 漂移：`doc/03-interfaces/skills-interface.md` 定义了 select()/match()/crystallize()/dissolve() 等方法，但未定义任何超时/资源上限相关方法，`SKILL_TIMEOUT` 错误码在 skills 层无实现落点。漂移正确解法为摘除该 Requirement（而非补实现），由 tool-use 统一承载执行超时/资源上限。

## What Changes

- 删除 `CORE-skills-R4` 超时与资源上限 Requirement（含 2 个 Scenario：执行超时中断、资源超限熔断）
- 删除该 Requirement 关联的 skills 层错误码 `SKILL_TIMEOUT` 与参数 `timeout_s=30`、`max_output=8192`（相关约束由 tool-use 承载，不新增）

## Impact

- **Affected specs**：`skills`（删除 CORE-skills-R4「超时与资源上限」）
- **Affected docs**：`openspec/specs/skills/spec.md`（删除 Requirement）、`openspec/changes/0031-skill-timeout-removal/`（新建三件套 + delta）
- **Affected code**：无（该 Requirement 无对应实现，删除不触达代码）
- **Dependencies**：tool-use 已承载执行超时/资源上限（timeout_s、max_output），无需新增能力；skills-interface 无超时/资源上限方法，无需改动
