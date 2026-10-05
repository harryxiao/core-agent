# SkillHub Specification Delta

## MODIFIED Requirements

### Requirement: 技能市场与技能发现
系统 SHALL 提供市场技能目录，支持按关键字搜索与按源列出；source 参数预留多源扩展，默认官方源。生产触达点 SHALL 为 CLI `skill search <query> [--source S]`，经 SkillHubClient 搜索市场并输出版本化元数据（不拉取完整技能体）；市场不可达或源不存在时 SHALL 报错并不改变任何状态。

#### Scenario: 搜索市场技能
- **GIVEN** 一个查询关键字
- **WHEN** SkillHubClient 搜索市场
- **THEN** 返回按匹配度排序的 Top-K MarketSkill 元数据（不拉取完整技能体）

#### Scenario: 按源列出目录
- **GIVEN** 一个已注册的 source
- **WHEN** MarketIndex.list 列出该源
- **THEN** 返回该源技能目录元数据

#### Scenario: CLI 搜索走技能市场
- **GIVEN** 市场中存在匹配技能的元数据
- **WHEN** 执行 `skill search <query>`（可带 `--source`）
- **THEN** 输出该技能的元数据（含版本），命令不改变运行态

### Requirement: 签名校验与可信下载
系统 SHALL 在下载技能前校验签名与来源可信度；下载的技能以 draft 状态注册，不自动启用。生产触达点 SHALL 为 CLI `skill install <skill_id> [--source S]`，经 SkillHubClient 下载（先校验后注册）；**CLI 侧技能库 SHALL 与组合根同源**（同一 `$CORE_STATE_DIR/skills.json`），使下载的 draft 技能可被后续会话见到；校验失败 SHALL 拒绝且不落盘。

#### Scenario: 签名校验失败拒绝
- **GIVEN** 下载技能的签名不匹配
- **WHEN** TrustVerifier 校验
- **THEN** 拒绝下载并返回 `SIGNATURE_INVALID`

#### Scenario: 下载默认 draft
- **GIVEN** 下载校验通过
- **WHEN** 技能注册到 SkillLibrary
- **THEN** 状态为 draft，不进入路由匹配，需显式激活后可用

#### Scenario: CLI 安装经签名校验且跨进程可见
- **GIVEN** 一份签名有效的市场技能
- **WHEN** 执行 `skill install <skill_id>`
- **THEN** 校验通过后以 draft 状态注册到**与组合根同源**的技能库（落盘），后续会话可读到；签名不匹配则拒绝、退出码非零，且技能库不落盘

#### Scenario: 市场未接入时如实报错
- **GIVEN** 未接入市场拉取（无 fetcher）
- **WHEN** 执行 `skill install <skill_id>`
- **THEN** 返回 `SIGNATURE_INVALID`（无法下载），退出码非零，不静默成功
