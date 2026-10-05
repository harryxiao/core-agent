# Observability Specification

## Purpose
可观测性与遥测让智能体每一步执行可追溯、可复盘，提供全链路日志、指标监控、链路追踪三大信号，同时作为进化引擎诊断与评测的数据源。

## Requirements

### Requirement: 全链路日志
系统 SHALL 记录模型输入/输出、工具调用、执行耗时与副作用，结构化且敏感信息脱敏。系统**组合根**（`build_runtime`）SHALL 在调用方**未注入** tracer 时装配**生产导出器**：把脱敏后的结构化事件以 JSONL **追加**落 `$CORE_STATE_DIR`（缺省 `~/.core/state`）的 trace 文件，并以**缓冲 / 退避重试导出器**包装 —— 导出失败降级为内存缓冲 + 溢出兜底，SHALL NOT 抛出、SHALL NOT 阻塞主循环。显式注入的 tracer SHALL **优先**（保持可覆盖，SUT/宿主可替换导出面）。事件 SHALL 可携带可选的**模块归因字段** `module_id`，标识产生该事件的**架构模块**（如 `loop.default`），供按模块聚合与缺陷归因；该字段 SHALL **可选且向后兼容**——未携带时既有的记录、序列化与消费语义 SHALL 逐字不变。

#### Scenario: 记录模型与工具调用
- **GIVEN** 一轮 loop 执行了模型推理和工具调用
- **WHEN** 遥测中心采集事件
- **THEN** 每个事件以结构化 JSONL 记录，含 trace_id/span_id/ts

#### Scenario: 敏感信息脱敏
- **GIVEN** 一个事件包含密钥等敏感值
- **WHEN** 写入日志
- **THEN** 敏感值被脱敏后才落盘（与 coeffect secret 标记联动）

#### Scenario: 组合根装配生产导出器
- **GIVEN** 一次未注入 tracer 的组合根装配
- **WHEN** `build_runtime` 完成装配并结束一条 trace
- **THEN** 事件以 JSONL 落盘到 `$CORE_STATE_DIR` 的 trace 文件，且导出经缓冲 / 退避重试包装（导出失败降级不阻塞主循环）

#### Scenario: 注入的 tracer 优先
- **GIVEN** 调用方显式注入一个 tracer
- **WHEN** `build_runtime` 装配
- **THEN** 使用注入的 tracer（SHALL NOT 被缺省生产导出器覆盖）

#### Scenario: 事件可携带模块归因
- **GIVEN** 一个由某架构模块**自身失败**产生的遥测事件
- **WHEN** 遥测中心采集该事件
- **THEN** 事件携带 `module_id` 指向该模块，消费方可据此把缺陷归因到模块级

#### Scenario: 未携带模块归因向后兼容
- **GIVEN** 一个不含模块归因的事件（既有四种 `kind` 路径）
- **WHEN** 记录与序列化该事件
- **THEN** `module_id` 缺省为空，且既有的 trace_id/span_id/ts/kind/payload 记录格式与消费语义逐字不变

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

### Requirement: 指标导出协议
系统 SHALL 以标准协议（OpenTelemetry / Prometheus）导出指标，供外部监控系统采集与聚合，指标命名与标签规范一致。

#### Scenario: OTel 导出
- **GIVEN** 指标监控已采集任务完成率/token/循环次数等指标
- **WHEN** 启用指标导出
- **THEN** 按 OpenTelemetry 协议导出，供外部采集器接收

#### Scenario: Prometheus 拉取
- **GIVEN** 指标已按规范命名并带标签
- **WHEN** Prometheus 拉取指标端点
- **THEN** 返回符合 Prometheus 文本格式的指标快照，标签与维度对齐

#### Scenario: 导出失败不阻塞
- **GIVEN** 指标导出失败
- **WHEN** 主循环继续执行
- **THEN** 导出降级重试，不阻塞主循环（复用遥测缓冲与导出重试机制）

### Requirement: 告警规则
系统 SHALL 支持分级告警规则：按严重级别（info/warning/critical）对指标阈值、错误率、资源异常等触发告警，并路由到通知渠道。

#### Scenario: 阈值触发告警
- **GIVEN** 某指标越过配置阈值
- **WHEN** 告警规则评估
- **THEN** 触发对应级别告警，记录事件并通知

#### Scenario: 分级告警
- **GIVEN** 不同类型异常事件
- **WHEN** 告警评估
- **THEN** 按严重级别分级（info/warning/critical），critical 优先通知

#### Scenario: 告警风暴抑制
- **GIVEN** 同一告警在短时间内重复触发
- **WHEN** 告警规则评估
- **THEN** 去重/抑制重复告警，避免告警风暴
