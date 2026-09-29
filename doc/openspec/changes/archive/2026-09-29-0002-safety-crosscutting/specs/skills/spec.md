
技能封装是"记忆即光谱"中 L3 技能段的管理层，负责原子技能库、版本管理与灰度/A/B、技能路由，是"结晶经济闭环"的上半场（下半场为 evolution 的溶解）。

## ADDED Requirements

### Requirement: 原子技能库
系统 SHALL 维护原子技能库，每个技能封装为可复用单元，含 schema、前置条件与执行说明。

#### Scenario: 技能注册校验
- **GIVEN** 一个待入库的技能定义
- **WHEN** 其 schema 非法
- **THEN** 拒绝入库并返回 `INVALID_SKILL_SCHEMA`

#### Scenario: 前置条件检查
- **GIVEN** 一个技能的前置条件不满足
- **WHEN** 尝试调用该技能
- **THEN** 调用被拒绝并返回 `PRECONDITION_FAILED`

### Requirement: 版本管理与灰度/A/B
系统 SHALL 支持技能世代版本、灰度发布与 A/B 测试，依据指标决定提升或回退。

#### Scenario: 灰度发布
- **GIVEN** 一个技能发布了新版本
- **WHEN** 新版本仅对部分任务生效
- **THEN** 观察 observability 指标后再决定全量或回退

#### Scenario: A/B 中 B 退化自动回退
- **GIVEN** 技能 A/B 并行测试中 B 指标显著退化
- **WHEN** A/B 对比完成
- **THEN** 自动切回 A，B 标记 deprecated

### Requirement: 技能路由
系统 SHALL 按任务类型自动匹配最合适技能，无匹配时回退通用流程。

#### Scenario: 路由命中 Top-K
- **GIVEN** 一个任务类型
- **WHEN** 路由器匹配技能
- **THEN** 返回匹配度排序的 Top-K 技能

#### Scenario: 路由未命中沉淀
- **GIVEN** 路由器无匹配技能
- **WHEN** 回退通用 loop
- **THEN** 记录未命中，供后续新技能沉淀

