# skillhub — spec delta（change 0133）

## MODIFIED Requirements

### Requirement: 签名校验与可信下载
系统 SHALL 在下载技能前校验签名与来源可信度；下载的技能以 draft 状态注册，不自动启用 —— 下载 SHALL NOT 使技能直接可路由，SHALL 经 skills 规格定义的**显式启用路径**（`draft → active`）方可进入路由匹配。生产触达点 SHALL 为 CLI `skill install <skill_id> [--source S]`，经 SkillHubClient 下载（先校验后注册）；**CLI 侧技能库 SHALL 与组合根同源**（同一 `$CORE_STATE_DIR/skills.json`），使下载的 draft 技能可被后续会话见到；校验失败 SHALL 拒绝且不落盘。CLI 侧的技能体拉取 SHALL 来自**本地市场制品库**（本地市场发布时入库的制品；离线、零凭据）；远端市场拉取仍为**凭证半**，未接入时 SHALL 如实报错，SHALL NOT 静默成功。

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
