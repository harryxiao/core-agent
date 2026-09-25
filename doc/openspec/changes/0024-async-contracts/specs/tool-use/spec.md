# Tool Use Specification

## Purpose

工具使用把模型动作转化为带 schema 的可执行调用，通过 coeffect 约束注入副作用契约，是"插件即原子"的运行时侧实现。调用入口同步（invoke）与异步（ainvoke）同构：异步为主、同步为薄壳，支持事件循环内非阻塞与真并发调用。

## ADDED Requirements

### Requirement: 异步工具调用
系统 SHALL 提供异步工具调用入口 ainvoke，与同步 invoke 共用统一请求 / 响应模型与 schema / coeffect 校验链路；ainvoke 支持事件循环内非阻塞调用与真并发，invoke 保留为薄壳（thin wrapper），内部经事件循环桥接调用对应异步实现，调用方无需感知事件循环、零改动。

#### Scenario: 异步调用入口
- **GIVEN** 内核 loop 运行于事件循环中，需并发执行多个工具
- **WHEN** 经 ainvoke 发起工具调用
- **THEN** 调用不阻塞事件循环，返回 awaitable，多个工具调用可并发执行

#### Scenario: 同步薄壳等价
- **GIVEN** 调用方处于同步上下文
- **WHEN** 调用 invoke 同步入口
- **THEN** 语义与 ainvoke 一致（含 schema 校验与 coeffect 副作用校验），内部经事件循环桥接完成调用，调用方无需改动

#### Scenario: 真并发执行
- **GIVEN** 多个相互独立的工具调用
- **WHEN** 经 ainvoke 并发发起
- **THEN** 各调用真并发执行（非串行阻塞），总耗时约等于最慢单个调用而非各调用耗时之和
