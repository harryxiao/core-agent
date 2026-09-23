# Observability Specification

## Purpose
可观测性与遥测让智能体每一步执行可追溯、可复盘，提供全链路日志、指标监控、链路追踪三大信号，同时作为进化引擎诊断与评测的数据源。

## Requirements

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

### Requirement: 遥测缓冲与导出重试
系统 SHALL 为遥测内存缓冲设置上限并提供溢出兜底，对导出失败按指数退避重试并施加背压，确保遥测故障不丢关键事件也不阻塞主循环。

#### Scenario: 缓冲溢出兜底
- **GIVEN** 遥测导出持续失败导致内存缓冲逼近上限
- **WHEN** 缓冲达到上限且仍有新事件进入
- **THEN** 按策略兜底（溢出事件落盘或按优先级丢弃低价值事件）并告警，缓冲不再无限增长

#### Scenario: 导出重试与背压
- **GIVEN** 遥测导出失败
- **WHEN** 主循环持续产生遥测事件
- **THEN** 按指数退避重试导出并施加背压（必要时降采样或暂停非关键采集），不阻塞主循环
