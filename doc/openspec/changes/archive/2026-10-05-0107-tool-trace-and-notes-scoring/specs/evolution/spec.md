# Evolution Specification Delta

## MODIFIED Requirements

### Requirement: 经验采集
系统 SHALL 从遥测数据中采集"行动→结果"成对证据，作为进化的唯一输入。采集 SHALL 覆盖**两类**证据来源：①工具调用类（按工具 id 归因）与②**带模块归因**的遥测事件（按事件携带的 `module_id` 归因为该**架构模块**）——后者使架构模块**自身失败**（如执行循环因预算耗尽失败）成为可诊断证据。既有工具调用通道的归因与产出语义 SHALL NOT 改变。①工具调用类通道 SHALL 由**执行循环在生产链路产出**（`kind="tool_call"` 遥测，见 loop「异步流式执行」），SHALL NOT 依赖仅有消费侧而无生产侧的纸面通道。**内部核心模块的 `plugin_id` SHALL 表示「归因对象身份」**（供进化引擎监控该模块与定位其缺陷），**SHALL NOT 蕴含**该模块已纳入 `PluginRegistry` 生命周期；模块自身的失败证据 SHALL 经**模块归因遥测通道**（`module_id`）承载，采集与诊断 SHALL NOT 要求该模块在注册表中可查。

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

#### Scenario: 工具调用通道在生产有产出
- **GIVEN** 一轮执行经执行循环产出了工具调用遥测（`kind="tool_call"`）
- **WHEN** 采集
- **THEN** 该证据按工具 id 归因为工具使用类，进入提案与诊断回路——通道在**生产**有输入，非仅消费侧就绪

#### Scenario: 内部模块归因不依赖注册表
- **GIVEN** 一个**未纳入** `PluginRegistry` 的内部核心模块（如 `loop.default`）产生了失败证据
- **WHEN** 采集与对比诊断
- **THEN** 仍能归因到该模块 id（证据经模块归因遥测通道承载、并按归因白名单判为架构级候选），不要求该模块在注册表中可查
