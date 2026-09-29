# LLM Provider Specification

## Purpose

LLM Provider（三方大模型归一化接入）让 core-agent 通过统一 LLMProvider 抽象接口调用任意三方大模型：配置任意模型 API Key 与 URL 即自动路由接入，LiteLLM 作默认实现、经依赖注入隔离可无缝替换或自研，调用方零改动。接口同步（completion / stream / embedding）与异步（acompletion / astream / aembedding）同构：异步为主、同步为薄壳，支持事件循环内非阻塞与真并发调用。

## ADDED Requirements

### Requirement: 异步调用接口
系统 SHALL 提供异步调用入口 acompletion / astream / aembedding，与同步入口（completion / stream / embedding）共用统一请求 / 响应模型；异步入口支持事件循环内非阻塞调用与真并发，同步入口保留为薄壳（thin wrapper），内部经事件循环桥接调用对应异步实现，调用方无需感知事件循环、零改动。

#### Scenario: 异步调用入口
- **GIVEN** 内核 loop 运行于事件循环中，需并发调用多个大模型
- **WHEN** 经 acompletion / astream / aembedding 发起请求
- **THEN** 调用不阻塞事件循环，返回 awaitable / 异步迭代器，多个调用可并发执行

#### Scenario: 同步薄壳等价
- **GIVEN** 调用方处于同步上下文
- **WHEN** 调用 completion / stream / embedding 同步入口
- **THEN** 语义与对应异步入口一致，内部经事件循环桥接（asyncio.run）完成调用，调用方无需改动、无需感知事件循环

#### Scenario: 真并发执行
- **GIVEN** 多个相互独立的模型调用
- **WHEN** 经异步入口并发发起
- **THEN** 各调用真并发执行（非串行阻塞），总耗时约等于最慢单个调用而非各调用耗时之和
