# skills — spec delta（change 0133）

## ADDED Requirements

### Requirement: 技能启用（draft → active）
系统 SHALL 提供把 `draft` 技能迁至 `active` 的**显式启用**路径，使下载 / 注册所得的草稿技能
**可被**启用（此前的迁移路径缺失 ⇒ `draft` 技能永不被路由，是死胡同）。启用 SHALL NOT 自动
发生：技能下载 / 注册后恒为 `draft`，须由显式动作驱动迁移。

- **入口**：`SkillLibrary.activate(skill_id)`；生产触达点 SHALL 为 CLI `skill activate <name>`，
  作用于**与组合根同源**的技能库（落盘），使启用跨进程可见。
- **放行集不变**：路由候选集 SHALL 仍只放行 `active` / `gray`（本能力**只补迁移路径**，SHALL NOT
  扩大路由放行集，SHALL NOT 使未启用的 `draft` 进入路由）。
- **幂等**：技能已为 `active` 时 SHALL no-op（返回该技能、状态不变、SHALL NOT 重复登记效应）。
- **未知 id**：SHALL 抛 `KeyError`（与 `lookup` / `remove` 同口径），SHALL NOT 静默创建新技能。
- **可逆**：注入效应追踪器时，启用 SHALL 登记可逆效应（回滚恢复启用前的状态）；未注入时
  SHALL NOT 登记（零行为变化，同 `SopExtractor` 的接缝口径）。

#### Scenario: draft 技能不进入路由
- **GIVEN** 一个以 `draft` 状态注册的技能，其 `task_types` 与任务词法命中
- **WHEN** 路由器匹配该任务
- **THEN** 该技能**不**进入候选集（放行集仍只含 `active` / `gray`）

#### Scenario: 显式启用后进入路由
- **GIVEN** 一个 `draft` 技能，其 `task_types` 与任务词法命中
- **WHEN** 对该技能执行显式启用
- **THEN** 其状态变为 `active`，且路由匹配该任务时**命中**该技能

#### Scenario: 重复启用幂等
- **GIVEN** 一个已 `active` 的技能
- **WHEN** 再次显式启用
- **THEN** 状态保持 `active`，且不产生第二条启用效应（幂等）

#### Scenario: 启用未知技能被拒绝
- **GIVEN** 一个未注册的 skill_id
- **WHEN** 请求启用
- **THEN** 抛 `KeyError`，且技能库**不**因此新增任何技能

#### Scenario: CLI 启用跨进程可见
- **GIVEN** 技能库中一个 `draft` 技能
- **WHEN** 执行 `skill activate <name>` 后由**另一个进程**装载同一技能库
- **THEN** 该技能状态为 `active`（启用已落盘，非进程内假象）；未注册的技能则退出码非零

#### Scenario: 启用效应可回滚
- **GIVEN** 一次启用在注入的效应追踪器上登记了效应
- **WHEN** 按该次登记的 trace 回滚
- **THEN** 该技能状态恢复为启用前状态（重复回滚不报错）
