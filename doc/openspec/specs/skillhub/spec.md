# SkillHub Specification

## Purpose
技能市场是"记忆即光谱"闭环的交换层：技能可发布到市场供其他实例下载，也可从市场获取他人沉淀的技能。本规格覆盖技能发现、多源路由与健康回退、签名校验与可信下载、发布审核流。

## Requirements

### Requirement: 技能市场与技能发现
系统 SHALL 提供市场技能目录，支持按关键字搜索与按源列出；source 参数预留多源扩展，默认官方源。

#### Scenario: 搜索市场技能
- **GIVEN** 一个查询关键字
- **WHEN** SkillHubClient 搜索市场
- **THEN** 返回按匹配度排序的 Top-K MarketSkill 元数据（不拉取完整技能体）

#### Scenario: 按源列出目录
- **GIVEN** 一个已注册的 source
- **WHEN** MarketIndex.list 列出该源
- **THEN** 返回该源技能目录元数据

### Requirement: 多源路由与健康回退
系统 SHALL 按 source 路由到对应市场源；源不健康时回退官方源，源不存在时拒绝路由。

#### Scenario: 源不可达回退
- **GIVEN** 某个 source 不可达
- **WHEN** MarketIndex 健康探测失败
- **THEN** 标记源不健康并回退官方源，返回 `SOURCE_UNHEALTHY`

#### Scenario: 源不存在
- **GIVEN** source 未注册
- **WHEN** 路由到该源
- **THEN** 返回 `SOURCE_NOT_FOUND`，不 fallback 到未知源

### Requirement: 签名校验与可信下载
系统 SHALL 在下载技能前校验签名与来源可信度；下载的技能以 draft 状态注册，不自动启用。

#### Scenario: 签名校验失败拒绝
- **GIVEN** 下载技能的签名不匹配
- **WHEN** TrustVerifier 校验
- **THEN** 拒绝下载并返回 `SIGNATURE_INVALID`

#### Scenario: 下载默认 draft
- **GIVEN** 下载校验通过
- **WHEN** 技能注册到 SkillLibrary
- **THEN** 状态为 draft，不进入路由匹配，需显式激活后可用

### Requirement: 技能发布与审核流
系统 SHALL 支持技能发布并经过审核流 `uploaded → pending → published/rejected`；发布通过后版本提升。

#### Scenario: 发布进入审核
- **GIVEN** 一个待发布的技能
- **WHEN** SkillPublisher.publish 上传
- **THEN** 状态为 uploaded，进入 pending 审核

#### Scenario: 审核通过发布
- **GIVEN** 技能处于 pending
- **WHEN** 审核 approved
- **THEN** 状态为 published，VersionManager 版本 v1→v2

#### Scenario: 审核驳回
- **GIVEN** 技能处于 pending
- **WHEN** 审核 rejected
- **THEN** 状态回退，允许修改后重传
