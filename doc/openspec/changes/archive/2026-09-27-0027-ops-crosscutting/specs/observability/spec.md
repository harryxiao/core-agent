# Observability Specification

## Purpose
可观测性与遥测让智能体每一步执行可追溯、可复盘，提供全链路日志、指标监控、链路追踪三大信号，同时作为进化引擎诊断与评测的数据源。

## ADDED Requirements

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
