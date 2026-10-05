# SkillHub Specification Delta

## MODIFIED Requirements

### Requirement: 技能市场与技能发现
系统 SHALL 提供市场技能目录，支持按关键字搜索与按源列出；source 参数预留多源扩展，默认官方源。生产触达点 SHALL 为 CLI `skill search <query> [--source S]`，经 SkillHubClient 搜索市场并输出版本化元数据（不拉取完整技能体）；市场不可达或源不存在时 SHALL 报错并不改变任何状态。市场目录 SHALL 可**落盘**（注入 `path`）：发布/审核写入的条目在**后续进程**的搜索与审核中可见；未注入 `path` 时为进程内目录（不落盘）。

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

#### Scenario: 市场目录跨进程可见
- **GIVEN** 一次发布已把技能元数据写入落盘的官方源目录
- **WHEN** **另一个进程**装载同一目录并列出/搜索该源
- **THEN** 命中该技能的元数据（落盘目录为市场真源，不依赖进程内内存）

### Requirement: 签名校验与可信下载
系统 SHALL 在下载技能前校验签名与来源可信度；下载的技能以 draft 状态注册，不自动启用。生产触达点 SHALL 为 CLI `skill install <skill_id> [--source S]`，经 SkillHubClient 下载（先校验后注册）；**CLI 侧技能库 SHALL 与组合根同源**（同一 `$CORE_STATE_DIR/skills.json`），使下载的 draft 技能可被后续会话见到；校验失败 SHALL 拒绝且不落盘。CLI 侧的技能体拉取 SHALL 来自**本地市场制品库**（本地市场发布时入库的制品；离线、零凭据）；远端市场拉取仍为**凭证半**，未接入时 SHALL 如实报错，SHALL NOT 静默成功。

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
- **GIVEN** 市场未接入拉取（无 fetcher）或本地市场无该技能制品
- **WHEN** 执行 `skill install <skill_id>`
- **THEN** 返回 `SIGNATURE_INVALID`（无法下载），退出码非零，不静默成功

#### Scenario: 制品被篡改则拒绝安装
- **GIVEN** 市场目录中某技能的元数据签名已登记，但本地市场**制品**（技能体）事后被篡改
- **WHEN** 执行 `skill install <skill_id>`
- **THEN** 末端验签不通过，返回 `SIGNATURE_INVALID`、退出码非零，且技能库不落盘

### Requirement: 技能发布与审核流
系统 SHALL 支持技能发布并经过审核流 `uploaded → pending → published/rejected`；发布通过后版本提升。生产触达点 SHALL 为 CLI `skill publish <skill_id> [--source S]`（上传本地已注册技能，进入 `pending` 审核）与 CLI `skill review <skill_id> <approved|rejected>`（审核决定）；发布 SHALL 同时把该技能存入**本地市场制品库**（使消费侧可拉取）；审核 SHALL **跨进程可续** —— 定位发布源的真源为**市场目录**（非进程内记忆）；审核通过后的版本提升 SHALL 落盘（`VersionManager` 的 `path` 与组合根同源）。技能未在本地注册、或源不存在时 SHALL 报错并不落盘。

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

#### Scenario: CLI 发布本地技能
- **GIVEN** 本地技能库中已注册一个技能
- **WHEN** 执行 `skill publish <skill_id>`
- **THEN** 该技能元数据（含签名）上架到指定源的市场目录、状态 pending，技能体入本地市场制品库；命令为一次性动作，不改变运行态；技能未在本地注册时退出码非零

#### Scenario: CLI 审核跨进程续接
- **GIVEN** 一次发布已在**上一个进程**完成（技能处于 pending）
- **WHEN** **另一个进程**执行 `skill review <skill_id> approved`
- **THEN** 从落盘市场目录定位该技能并置为 published、市场版本递增且版本提升落盘；未发布（目录中不存在）的技能退出码非零

#### Scenario: 供给侧闭环可被消费
- **GIVEN** 一条本地技能已经 `skill publish` 上架
- **WHEN** 依次执行 `skill search <query>` 与 `skill install <skill_id>`
- **THEN** 搜索命中该技能元数据，安装经签名校验通过后以 draft 落盘 —— 「本地技能 → 发布 → 索引 → 消费侧 search/install」闭环成立
