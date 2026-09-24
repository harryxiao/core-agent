
可观测性与遥测让智能体每一步执行可追溯、可复盘，提供全链路日志、指标监控、链路追踪三大信号，同时作为进化引擎诊断与评测的数据源。

## ADDED Requirements

### Requirement: 全链路日志
系统 SHALL 记录模型输入/输出、工具调用、执行耗时与副作用，结构化且敏感信息脱敏。

#### Scenario: 记录模型与工具调用
- **GIVEN** 一轮 loop 执行了模型推理和工具调用
- **WHEN** 遥测中心采集事件
- **THEN** 每个事件以结构化 JSONL 记录，含 trace_id/span_id/ts

#### Scenario: 敏感信息脱敏
- **GIVEN** 一个事件包含密钥等敏感值
- **WHEN** 写入日志
- **THEN** 敏感值被脱敏后才落盘（与 coeffect secret 标记联动）

### Requirement: 指标监控
系统 SHALL 采集任务完成率、token 消耗、循环次数、错误率等性能指标，并按 trace_id/plugin_id 聚合。

#### Scenario: 指标聚合快照
- **GIVEN** 多个任务已执行
- **WHEN** 查询指标快照
- **THEN** 返回按维度聚合的完成率/token/循环次数/错误率

### Requirement: 链路追踪
系统 SHALL 为每个任务分配 trace_id，贯穿执行全链路，支持单任务全流程回溯。

#### Scenario: 单任务全链路回溯
- **GIVEN** 一个任务已完成并带有 trace_id
- **WHEN** 调用 Tracer.replay(trace_id)
- **THEN** 按时间序重放该任务所有事件，可定位失败环节

#### Scenario: 遥测故障不阻塞主循环
- **GIVEN** 遥测导出失败
- **WHEN** 主循环继续执行
- **THEN** 遥测降级为内存缓冲异步落盘，不阻塞主循环

