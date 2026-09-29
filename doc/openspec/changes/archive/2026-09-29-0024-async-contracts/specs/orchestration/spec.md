# Orchestration Specification

## Purpose

任务规划与编排把单一循环升级为可处理长周期复杂任务的执行引擎，提供状态机管理、子任务拆解、多 Agent 协同三层基础能力，并新增并行扇出、目标监控、优先级调度三项运行时能力，确保复杂目标可并行推进、可量化校验、可按优先级调度。并行扇出的执行单元显式复用异步接口（acompletion / ainvoke），消除同步串行阻塞。

## ADDED Requirements

### Requirement: 异步执行单元契约
系统 SHALL 明确并行扇出的执行单元契约：扇出派发的每个执行单元复用 llm-provider 的 acompletion 与 tool-use 的 ainvoke 异步接口，支持事件循环内非阻塞与真并发执行，消除同步串行阻塞；同一波次内无依赖子任务经异步接口并发派发，不再是串行阻塞。

#### Scenario: 执行单元复用异步接口
- **GIVEN** 并行扇出派发某波次内的无依赖子任务
- **WHEN** 执行单元发起模型调用或工具调用
- **THEN** 复用 acompletion / ainvoke 异步接口，而非同步 completion / invoke

#### Scenario: 扇出真并发非阻塞
- **GIVEN** 同一波次内多个无依赖子任务
- **WHEN** fan-out 经异步接口并发派发
- **THEN** 各执行单元真并发执行且不阻塞事件循环，总耗时约等于最慢单个执行单元而非各单元耗时之和

#### Scenario: 契约空白闭合
- **GIVEN** 扇出执行单元与 LLMProvider / ToolProvider 异步能力之间存在契约空白
- **WHEN** 本契约显式映射执行单元到异步接口
- **THEN** 并行编排与异步能力之间的契约空白被闭合，扇出场景不再退化为同步串行阻塞
