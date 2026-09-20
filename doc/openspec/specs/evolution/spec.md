# Evolution Specification

## Purpose
进化引擎实现"进化即结晶"的结晶经济闭环：闭环主干为四阶段——对比诊断（Diagnoser 归因到单个插件）→ 模块级提案（Proposer 生成世代化候选）→ 验证门（Validator 执行 review + 运行时测试）→ 留出评测（Evaluator 防退化）——在此基础上把行动经验结晶为技能/SOP、把无效技能溶解回收，使能力以可复用资产形式沉淀。

## Requirements

### Requirement: 经验采集
系统 SHALL 从遥测数据中采集"行动→结果"成对证据，作为进化的唯一输入。

#### Scenario: 采集行动结果对
- **GIVEN** 一个任务执行完成
- **WHEN** 进化引擎扫描 trace
- **THEN** 提取 action/result 成对证据，附任务类型与指标

#### Scenario: 无结果证据不采集
- **GIVEN** 一个行动没有可观测结果
- **WHEN** 采集
- **THEN** 跳过，不产生虚假经验

### Requirement: 结晶为技能/SOP
系统 SHALL 把高频成功模式结晶为技能/SOP，并生成带验收标准的单元。

#### Scenario: 生成技能候选
- **GIVEN** 某模式跨 N 个任务成功率达标
- **WHEN** 结晶器运行
- **THEN** 生成技能候选，含 schema/前置条件/验收标准

#### Scenario: 候选待人工确认
- **GIVEN** 一个技能候选生成
- **WHEN** 入库前
- **THEN** 进入评审队列，通过后入 skills 库（与权限审批流联动）

### Requirement: 溶解与回收
系统 SHALL 检测退化的技能/SOP，评估后标记废弃或回收。

#### Scenario: 退化检测
- **GIVEN** 一个技能连续指标退化
- **WHEN** 进化引擎评估
- **THEN** 标记 deprecated，停止路由

#### Scenario: 回收回记忆池
- **GIVEN** 一个技能被判定长期失效
- **WHEN** 溶解器运行
- **THEN** 其有效片段回收为事实/经验，回写记忆层

### Requirement: 对比诊断
系统 SHALL 把缺陷定位到单个插件级别，作为进化闭环的起点。

#### Scenario: 归因到插件
- **GIVEN** 一批任务 trace 含失败证据
- **WHEN** Diagnoser 运行诊断
- **THEN** 输出 DiagnosisReport，归因到 target_plugin（None 表示系统级）

#### Scenario: 无插件级归因则人工介入
- **GIVEN** 诊断无法归因到单一插件
- **WHEN** target_plugin 为 None
- **THEN** 转人工处理，不进入提案阶段

### Requirement: 模块级提案
系统 SHALL 针对诊断结果生成世代化产物（技能/插件补丁 + delta）。

#### Scenario: 生成候选
- **GIVEN** 一个 DiagnosisReport 已归因到插件
- **WHEN** Proposer 运行
- **THEN** 生成 GenerationCandidate，含 delta 与 kind（skill/plugin）

#### Scenario: 候选进入验证门
- **GIVEN** 候选已生成
- **WHEN** 发布前
- **THEN** 交 Validator 验证，未过门不发布

### Requirement: 验证门
系统 SHALL 对候选执行 review + 运行时测试，通过才允许发布。

#### Scenario: 过门发布
- **GIVEN** 一个候选提交验证
- **WHEN** review 与运行时测试均通过
- **THEN** GateReport.passed=True，候选进入留出评测

#### Scenario: 未过门丢弃
- **GIVEN** 候选未通过验证门
- **WHEN** Validator 判定失败
- **THEN** 丢弃候选，教训写回 L2/L3

### Requirement: 留出评测
系统 SHALL 在留出集上评测候选，防止过拟合与退化。

#### Scenario: 留出集通过则发布
- **GIVEN** 候选通过验证门
- **WHEN** Evaluator 留出集评测不退化
- **THEN** verdict=publish，结晶入库

#### Scenario: 留出集退化回滚
- **GIVEN** 候选在留出集上退化
- **WHEN** Evaluator 判定退化
- **THEN** verdict=rollback，自动回滚并冻结冷却期
