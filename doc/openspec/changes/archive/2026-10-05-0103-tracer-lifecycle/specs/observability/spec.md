# Observability Specification Delta

## MODIFIED Requirements

### Requirement: 链路追踪
系统 SHALL 为每个任务分配 `trace_id`，贯穿执行全链路。`Tracer` SHALL **只保留在途（未封口）trace 的事件**：
`start_trace` 建链、`record` 追加事件、`end_trace` **封口**——封口 SHALL 把该链路事件交付**导出器**
（**落盘为真源**），并 SHALL **从内存缓冲移除**该链路事件；`Tracer` 的内存占用 SHALL **不随已封口 trace
数增长**。`replay(trace_id)` SHALL 服务**在途** trace（回放同进程内**未封口**链路按时间序的事件，
支持执行中定位失败环节）；**已完成**任务的回溯 SHALL 以**落盘遥测**（导出器产出）为**真源**，
SHALL NOT 依赖已封口 trace 的内存残留。

#### Scenario: 单任务全链路回溯
- **GIVEN** 一个任务**执行中**并带有 trace_id
- **WHEN** 调用 Tracer.replay(trace_id)
- **THEN** 按时间序重放该任务**已记录**的全部事件，可定位失败环节

#### Scenario: 封口交付导出器并释放内存
- **GIVEN** 一条在途 trace 已记录若干事件，且 Tracer 装配了导出器
- **WHEN** 调用 Tracer.end_trace(trace_id)
- **THEN** 该链路事件被交付导出器，且**从内存缓冲移除**（此后 replay 该 trace 返回空）

#### Scenario: 已完成任务回溯以落盘为真源
- **GIVEN** 一个任务已完成、已封口，其事件已由导出器产出
- **WHEN** 需要回溯该任务的执行全链路
- **THEN** 以**落盘遥测**为真源回溯，不依赖内存残留

#### Scenario: 内存不随已封口 trace 增长
- **GIVEN** 连续执行多轮，每轮开一条 trace 并在收尾封口
- **WHEN** 全部轮次结束
- **THEN** Tracer 的内存缓冲不随轮次增长（已封口 trace 不驻留）

#### Scenario: 遥测故障不阻塞主循环
- **GIVEN** 遥测导出失败
- **WHEN** 主循环继续执行
- **THEN** 遥测降级为内存缓冲异步落盘，不阻塞主循环
