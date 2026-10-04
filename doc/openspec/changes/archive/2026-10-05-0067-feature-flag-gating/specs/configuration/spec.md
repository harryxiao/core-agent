# configuration spec delta — feature-flag-gating

**把「功能开关」从纸面契约落成运行时门控。** 规格要求「关闭的模块不加载、不初始化」，而组合根
`build_runtime` 无条件构造全部模块、`ConfigManager.is_enabled` 零生产调用方 ⇒ 契约无落点（账本 E10）。

**用户裁决（2026-10-05）：白名单内的可选模块缺省开**（兼容现状：未声明即装配），只有显式
`features.<模块>: false` 才不装配。原文「缺省关闭」口径随之订正（`coding-plan/phase-0.md` 的
未勾验收框同改）。

## MODIFIED Requirements

### Requirement: 功能开关（feature flag）
系统 SHALL 支持模块级 feature flag：关闭的模块不加载、不初始化，实现功能裁剪。feature flag SHALL ONLY 作用于**模块装配** —— 即组合根是否构造该模块的实例、是否注册其随装配产生的副作用（技能注册、状态文件读取）、是否接通其 CLI 与 Web UI 入口；SHALL NOT 改变模块**自身**的二级启用开关（如 `pet.enabled` 决定宠物模式是否启用，其缺省与语义不由 feature flag 改变）。**缺省口径**：白名单内的可选模块**未声明即视为开启**（缺省装配，保持既有行为）；只有显式 `false`（yaml `features.<模块>: false`、env `CORE_FEATURE_<模块>`、CLI `--feature <模块>=false`）SHALL 使该模块**完全不装配**。门控名单 SHALL 由组合根以**单一真源**维护（当前为 `pet` / `beast` / `evolution`）；名单外的模块名 SHALL NOT 触发任何装配裁剪，SHALL NOT 影响核心面。

#### Scenario: 关闭模块不初始化
- **GIVEN** features 段将某模块（如 voice_output）设为 false
- **WHEN** 系统启动
- **THEN** 该模块不加载、不初始化，其依赖资源不占用

#### Scenario: 开启模块正常初始化
- **GIVEN** features 段将某模块设为 true
- **WHEN** 系统启动
- **THEN** 该模块按正常流程初始化

#### Scenario: 未声明即装配（缺省开）
- **GIVEN** 配置的 features 段未声明某门控名单内模块（或无 features 段）
- **WHEN** 系统启动装配
- **THEN** 该模块按正常流程装配（与显式 `true` 等价）

#### Scenario: 关闭模块的装配面为空
- **GIVEN** features 段将门控名单内某模块设为 false（如 `pet: false`）
- **WHEN** 系统启动装配
- **THEN** 组合根不构造该模块的任何实例、不产生其装配期副作用（不注册其技能、不读其状态文件），运行系统在该面的字段为空，且该模块的 CLI 入口拒绝执行并说明原因

#### Scenario: feature flag 不改变模块自身启用开关
- **GIVEN** `features.pet` 未声明（缺省开）而 `pet.enabled` 为 false
- **WHEN** 系统启动装配并调用 `pet` CLI
- **THEN** 模块**已装配**（装配面非空），`pet` CLI 仍按 `pet.enabled` 报「未启用」—— 两级开关各管各的，互不覆盖

#### Scenario: 核心模块不受 feature flag 影响
- **GIVEN** features 段把门控名单内全部模块设为 false
- **WHEN** 系统启动装配
- **THEN** 循环 / 记忆 / 工具 / 技能路由等核心面照常装配，系统仍可正常跑一轮
