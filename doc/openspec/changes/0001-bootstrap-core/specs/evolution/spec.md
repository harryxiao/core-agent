
进化引擎实现"进化即结晶"的结晶经济闭环下半场：把行动经验结晶为技能/SOP、把无效技能溶解回收，使能力以可复用资产形式沉淀。

## ADDED Requirements

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
