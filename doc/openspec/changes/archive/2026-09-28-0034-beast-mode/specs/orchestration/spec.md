# Orchestration Specification

## Purpose

任务规划与编排把单一循环升级为可处理长周期复杂任务的执行引擎，提供状态机管理、子任务拆解、多 Agent 协同三层基础能力，并新增并行扇出、目标监控、优先级调度三项运行时能力，确保复杂目标可并行推进、可量化校验、可按优先级调度。并行扇出的执行单元显式复用异步接口（acompletion / ainvoke），消除同步串行阻塞。

## MODIFIED Requirements

### Requirement: 多 Agent 协同
系统 SHALL 支持按任务类型路由到最合适的子 Agent，并通过标准化消息协议完成交接；handoff 异步执行子 Agent（经 loop.arun，非阻塞，支持多 Agent 并发）并返回完整 LoopResult（含 reply / trace_id / failed），供调用方判定任务成败。

#### Scenario: 能力匹配与交接
- **GIVEN** 一个子任务需要特定能力
- **WHEN** 路由器匹配到合适的子 Agent
- **THEN** 通过 TaskHandoff 交接，交接上下文由 context 模块打包

#### Scenario: 交接返回完整结果
- **GIVEN** 一个子任务经 handoff 交接给子 Agent
- **WHEN** 子 Agent 异步执行完成
- **THEN** handoff 返回完整 LoopResult（含 reply / trace_id / failed），调用方可据 failed 判定成败

#### Scenario: 无匹配 Agent
- **GIVEN** 没有子 Agent 能处理当前子任务
- **WHEN** 路由器返回无匹配
- **THEN** 降级到备用 Agent 或转人工审批
