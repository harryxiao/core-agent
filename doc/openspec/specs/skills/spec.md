# Skills Specification

## Purpose
技能封装是"记忆即光谱"中 L3 技能段的管理层，负责原子技能库、版本管理与灰度/A/B、技能路由，是"结晶经济闭环"的上半场（下半场为 evolution 的溶解）。

## Requirements

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

### Requirement: SOP 提炼（skill extraction）
系统 SHALL 提供 SOP 提炼能力：由注入的提炼器（DI 可调用，缺省不启用）把**同一类任务的
成功轨迹**聚合、提炼为一条 `Skill`（`instructions` 承载 SOP 步骤、`task_types` 承载归组键），
并 SHALL 经 `SkillLibrary.register()` 入库（复用既有 schema 校验），入库 SHALL 可逆。

- **触发**：任务**成功**收尾时提交「任务文本 + 行动/结果序列」；失败轨迹 SHALL 不计入累积。
- **阈值**：同一组累计达阈值（缺省 3 条）才提炼一次，提炼后 SHALL 清空该组（下批重新累积）。
- **归组**：SHALL 优先词法命中已有技能的 `task_types` 并复用其作组键；未命中时以任务词元签名
  为新组键。归组口径 SHALL 确定性（离线可断言）。
- **发布**：提炼产物 SHALL 以 `active` 入库（维度1 技能库属低风险自动发布）；提炼文本为空时
  SHALL 不入库。
- 未注入提炼器时 SHALL 不累积、不提炼（零额外调用）；提炼失败 SHALL NOT 中断 Agent 主流程。

#### Scenario: 同类任务达阈值提炼入库
- **GIVEN** 已注入提炼器与技能库，同一类任务成功执行 3 次（阈值）
- **WHEN** 第 3 次成功收尾触发提炼
- **THEN** 技能库新增一条 `Skill`：`instructions` 为提炼文本、`task_types` 含组键、
  `status="active"`；该技能可被 `SkillRouter.match` 命中

#### Scenario: 未达阈值不提炼
- **GIVEN** 同一类任务成功执行次数少于阈值
- **WHEN** 每次成功收尾触发观察
- **THEN** 技能库不新增技能（仅累积样本）

#### Scenario: 失败轨迹不计入累积
- **GIVEN** 同一类任务连续失败（`ok=False`）
- **WHEN** 收尾触发观察
- **THEN** 不累积样本、不提炼（失败轨迹不是 SOP）

#### Scenario: 归组复用已有技能的 task_types
- **GIVEN** 技能库已有一条 `task_types=["report summarize"]` 的技能
- **WHEN** 新任务 "summarize report" 收尾且词法命中该 task_type
- **THEN** 样本归入该 `task_type` 组键（而非新建任务词元签名组）

#### Scenario: 未注入提炼器时降级
- **GIVEN** 未注入提炼器（未配置模型）
- **WHEN** 任务成功收尾
- **THEN** 不累积、不提炼、无额外模型调用，主流程不受影响

#### Scenario: 空提炼不入库
- **GIVEN** 已注入提炼器，样本达阈值
- **WHEN** 提炼返回空文本
- **THEN** 不入库（不写半成品），样本保留待下轮

#### Scenario: 提炼入库可逆
- **GIVEN** 一次提炼已入库一条技能
- **WHEN** 按该次登记的 trace 回滚效应
- **THEN** 技能从库中移除（重复回滚不报错）
