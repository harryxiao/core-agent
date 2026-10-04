# Evolution Specification

## Purpose
进化引擎实现"进化即结晶"的结晶经济闭环：闭环主干为四阶段——对比诊断（Diagnoser 归因到单个插件）→ 模块级提案（Proposer 生成世代化候选）→ 验证门（Validator 执行 review + 运行时测试）→ 留出评测（Evaluator 防退化）——在此基础上把行动经验结晶为技能/SOP、把无效技能溶解回收，使能力以可复用资产形式沉淀。验证门与留出评测依托可落地的评测基建（基准集 + 评测运行器 + 指标对比基线）工程化执行，并扩展到对任意任务的通用质量评测（任务完成度、正确性、轨迹质量），复用同一套评测基建。

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

#### Scenario: 并发评测资源上限
- **GIVEN** 多个候选同时进入留出评测
- **WHEN** 并发评测请求超过资源配额上限
- **THEN** 超限请求排队或限流，评测资源总量受配额约束，不因并发耗尽资源导致评测结果失真


### Requirement: 评测基建
系统 SHALL 提供可落地的评测基建（基准集 + 评测运行器 + 指标对比基线），支撑验证门与留出评测的工程化执行。

#### Scenario: 基准集注册
- **GIVEN** 一个评测基准（含输入样例与期望指标）准备就绪
- **WHEN** 进化引擎或运维注册该基准
- **THEN** 基准入库并可被留出评测按需引用

#### Scenario: 候选批量评测
- **GIVEN** 一个候选通过验证门
- **WHEN** Evaluator 运行评测
- **THEN** 评测运行器在留出集上批量执行，产出候选指标报告

#### Scenario: 与基线对比判定退化
- **GIVEN** 候选评测指标与当前基线指标均已采集
- **WHEN** Evaluator 对比二者
- **THEN** 不退化则 publish，退化则 rollback，指标差异归档供诊断归因

### Requirement: 任务质量评测
系统 SHALL 对任意任务提供通用质量评测，从任务完成度、正确性、轨迹质量三个维度量化任务执行质量，复用评测基建（基准集 + 评测运行器 + 指标对比基线）工程化执行。

#### Scenario: 任务完成度评测
- **GIVEN** 一个任务执行结束并产出结果
- **WHEN** 评测运行器对任务执行质量评测
- **THEN** 产出完成度指标（目标达成情况），判定任务是否达标

#### Scenario: 正确性评测
- **GIVEN** 一个任务的结果与基准集期望答案
- **WHEN** 评测运行器对比结果与期望
- **THEN** 产出正确性指标（对错或得分），错误归因到失败环节

#### Scenario: 轨迹质量评测
- **GIVEN** 一个任务的完整执行轨迹
- **WHEN** 评测运行器分析轨迹
- **THEN** 产出轨迹质量指标（无效步骤、回退次数等），供诊断与优化

### Requirement: 架构级候选强制人工审批（HITL confirm gate）
系统 SHALL 按风险域区分候选的确认路径：世代化候选 SHALL 携带 `risk_level`（`high` 为架构级——
`kind="plugin"`，`low` 为技能库级——`kind="skill"`）。`risk_level="high"` 的候选 SHALL 强制走
**人工审批**：`confirm` SHALL 要求一张与候选目标一致的**已批准**权限审批单，缺失、未批准或目标
不符时 SHALL NOT 放行（fail-closed，候选保持 `pending`）；`risk_level="low"` 的候选 SHALL 仍须
**显式**人工 `confirm()`——系统 SHALL NOT 提供低风险自动结晶。

- **判定**：`risk_level` SHALL 由提案阶段按 `kind` 判定并随候选固化（不依赖调用方传入）。
- **门禁**：审批判定 SHALL 由 permission 域解释其审批单状态（域外 SHALL NOT 依赖状态字面量）。
- **可追溯**：审批单 SHALL 携带候选目标与 trace，经审批流归档可回溯。
- **拒绝不放行**：被拒/过期/超时的审批单 SHALL NOT 放行候选；`crystallize` 对未确认候选仍 SHALL
  拒绝（既有 `CANDIDATE_PENDING` 语义不变）。

#### Scenario: 架构级候选无审批单不放行
- **GIVEN** 一个 `risk_level="high"` 的候选已过验证门与留出评测
- **WHEN** 不带审批单调用 `confirm`
- **THEN** 抛结构化错误 `CONFIRM_REQUIRED`，候选 `status` 保持 `pending`，`crystallize` 拒绝

#### Scenario: 架构级候选带已批准审批单放行
- **GIVEN** 一个 `risk_level="high"` 的候选，且已有一张目标一致、经人工批准的审批单
- **WHEN** 携带该审批单调用 `confirm`
- **THEN** 候选 `status` 置 `confirmed`，`crystallize` 可发布

#### Scenario: 审批被拒不放过
- **GIVEN** 一个 `risk_level="high"` 的候选，审批单已被人工拒绝
- **WHEN** 携带该审批单调用 `confirm`
- **THEN** 抛 `CONFIRM_REQUIRED`，候选保持 `pending`

#### Scenario: 审批单目标不符不放行
- **GIVEN** 一张已批准但目标为**其他**插件的审批单
- **WHEN** 携带它确认本候选
- **THEN** 抛 `CONFIRM_REQUIRED`，候选保持 `pending`（不得跨候选复用审批）

#### Scenario: 技能级候选仍须显式人工确认
- **GIVEN** 一个 `risk_level="low"` 的候选（`kind="skill"`）
- **WHEN** 调用 `confirm`（不带审批单）
- **THEN** 候选置 `confirmed`（人工确认仍是必要条件，只是不要求权限工单），未被确认时
  `crystallize` 仍拒绝

### Requirement: 观察期回归自动溶解（auto-dissolve）
系统 SHALL 在**结晶发布后**为该产物开启**观察期窗口**（记录发布时评测基线分），并由调用方持续
采样发布后的回归指标：观察样本数达下限**且**观察均分低于「基线 − 容差」时 SHALL **自动溶解**
（技能标 `deprecated`、停止路由，教训 SHALL 写回记忆层并携带回归证据）。溶解后该目标 SHALL 进入
**冻结冷却期**，期内 SHALL NOT 再次触发溶解。

- **开窗**：仅**已发布**（`crystallize` 成功）的产物开窗；未开窗目标的采样 SHALL 被忽略
  （不抛异常，也不累积）。
- **判定**：容差为**绝对分差**（与留出评测的 margin 同一形状）；样本数不足时 SHALL NOT 判定回归。
- **冻结**：冻结期内 SHALL NOT 累积样本、SHALL NOT 触发溶解；冷却期结束 SHALL 自动恢复采样。
- **可追溯**：自动溶解的回归证据（基线 / 观察均分 / 样本数）SHALL 随教训条目留痕。
- 两维度通用：技能级与架构级候选的结晶产物 SHALL 同等开窗。

#### Scenario: 回归超阈值自动溶解并保留教训
- **GIVEN** 一个已结晶发布的产物已开窗（基线分 1.0），观察样本达下限且均分低于「基线 − 容差」
- **WHEN** 采样触发判定
- **THEN** 自动 `dissolve`：对应技能标 `deprecated`，教训条目写回记忆层且含基线/均分/样本数

#### Scenario: 样本不足不判定
- **GIVEN** 观察样本数少于下限（即使单次分数远低于基线）
- **WHEN** 采样
- **THEN** 不判回归、不溶解（仅累积样本）

#### Scenario: 未回归不溶解
- **GIVEN** 观察均分不低于「基线 − 容差」
- **WHEN** 采样达下限
- **THEN** 不溶解，技能保持 `active`

#### Scenario: 冻结期内不再触发
- **GIVEN** 一次自动溶解已发生，目标处于冻结冷却期
- **WHEN** 冷却期内继续采样（即使分数远低于基线）
- **THEN** 不累积样本、不再触发溶解；冷却期结束后恢复采样

#### Scenario: 未开窗目标的采样被忽略
- **GIVEN** 一个从未结晶发布（未开窗）的目标
- **WHEN** 调用采样
- **THEN** 忽略该样本（不抛异常、不建窗、不溶解）
