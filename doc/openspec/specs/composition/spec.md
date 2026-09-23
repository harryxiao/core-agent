# Composition Specification

## Purpose

Composition（组合与分发层）是 CORE-Harness 唯一的静态层：只有组合代数、没有业务逻辑、永不进化。它通过 profile（命名组合）/ bundle（分发格式）/ patch.yml（用户覆盖）三要素，把已结晶的技能与插件按需组合、跨部署分发、按用户差异覆盖，实现「一切皆插件 + 可逆组合」的基底（来源：core_harness_architecture.md L5）。

## Requirements

### Requirement: profile 命名组合
系统 SHALL 提供 profile 命名组合机制（如 web / headless / sdk-minimal），一个 profile 命名一个可复用的插件组合集合，层叠多个 bundle 并叠加用户 patch.yml。

#### Scenario: 按名选用组合
- **GIVEN** 系统已定义若干命名 profile
- **WHEN** 用户或部署按名选用某个 profile
- **THEN** 系统按该 profile 声明的组合解析出完整插件集

### Requirement: bundle 分发格式
系统 SHALL 定义 bundle 作为插件的分发格式，使已结晶的技能可打包、跨部署复用。

#### Scenario: 跨部署复用
- **GIVEN** 某部署结晶出一批技能
- **WHEN** 将技能打包为 bundle
- **THEN** 其他部署可引入该 bundle 复用同一批技能，无需重新结晶

#### Scenario: bundle 校验失败
- **GIVEN** 引入的 bundle 校验和或签名不符、或格式损坏
- **WHEN** 部署引入该 bundle
- **THEN** 拒绝加载并报错定位损坏 bundle，不影响已有组合，可回退到引入前状态

#### Scenario: 循环依赖检测
- **GIVEN** 多个 bundle 间声明引用形成循环依赖
- **WHEN** 解析 bundle 依赖图
- **THEN** 检测到环则拒绝加载并报错指出环路径，不进入死循环，已有组合不受影响


### Requirement: patch.yml 用户覆盖
系统 SHALL 支持用户 patch.yml 对 profile 组合做局部覆盖，在不改 profile 与 bundle 的前提下按用户差异调整。

#### Scenario: 用户差异覆盖
- **GIVEN** 用户对某 profile 有局部差异需求
- **WHEN** 提供 patch.yml 声明覆盖项
- **THEN** 系统在 profile 组合结果上应用覆盖，原 profile 与 bundle 保持不变

#### Scenario: 覆盖冲突兜底
- **GIVEN** patch.yml 覆盖项与 profile/bundle 既有项冲突或产生歧义
- **WHEN** 解析覆盖无法唯一判定生效项
- **THEN** 按确定优先级裁决（显式 patch 覆盖优先于默认层叠），仍歧义则报错并回退到覆盖前状态，不静默吞掉冲突


### Requirement: 层叠解析
系统 SHALL 按「bundle 层叠 + patch.yml 覆盖」的确定顺序解析最终组合，解析结果可逆、可回退。

#### Scenario: 确定顺序解析
- **GIVEN** 一个 profile 层叠多个 bundle 并叠加 patch.yml
- **WHEN** 解析最终组合
- **THEN** 按确定顺序合并，同名项由 patch.yml 覆盖，卸载时可回退到覆盖前状态
