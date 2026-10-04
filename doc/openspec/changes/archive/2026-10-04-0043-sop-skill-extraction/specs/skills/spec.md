# Skills Specification Delta

## ADDED Requirements

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
