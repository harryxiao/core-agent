# Evolution Specification Delta

## MODIFIED Requirements

### Requirement: 经验采集
系统 SHALL 从遥测数据中采集"行动→结果"成对证据，作为进化的唯一输入。采集 SHALL 覆盖**两类**证据来源：①工具调用类（按工具 id 归因）与②**带模块归因**的遥测事件（按事件携带的 `module_id` 归因为该**架构模块**）——后者使架构模块**自身失败**（如执行循环因预算耗尽失败）成为可诊断证据。既有工具调用通道的归因与产出语义 SHALL NOT 改变。

#### Scenario: 采集行动结果对
- **GIVEN** 一个任务执行完成
- **WHEN** 进化引擎扫描 trace
- **THEN** 提取 action/result 成对证据，附任务类型与指标

#### Scenario: 无结果证据不采集
- **GIVEN** 一个行动没有可观测结果
- **WHEN** 采集
- **THEN** 跳过，不产生虚假经验

#### Scenario: 模块失败采集为可归因证据
- **GIVEN** 一个携带模块归因（`module_id`）的失败遥测事件
- **WHEN** 采集
- **THEN** 产出可归因到该模块的证据（`success` 为假），供对比诊断定位到该架构模块

#### Scenario: 既有工具通道归因不变
- **GIVEN** 一个工具调用事件
- **WHEN** 采集
- **THEN** 仍按工具 id 归因并产出工具使用类证据，与既有行为逐字一致
