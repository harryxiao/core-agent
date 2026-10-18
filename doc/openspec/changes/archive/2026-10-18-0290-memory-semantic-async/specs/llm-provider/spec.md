# llm-provider — 同步薄壳的循环安全桥接（change 0290）

## MODIFIED Requirements

### Requirement: 异步调用接口
系统 SHALL 提供异步调用入口 acompletion / astream / aembedding，与同步入口（completion / stream / embedding）共用统一请求 / 响应模型；异步入口支持事件循环内非阻塞调用与真并发，同步入口保留为薄壳（thin wrapper），内部经事件循环桥接调用对应异步实现，调用方无需感知事件循环、零改动。

同步薄壳在**无运行事件循环**时 SHALL 直接 `asyncio.run` 执行对应异步实现；在**运行中事件循环**内 SHALL 在一次性工作线程的新事件循环中执行同一异步实现并等待结果，SHALL NOT 抛出 `asyncio.run()` 嵌套错误、SHALL NOT 留下未等待（never awaited）协程。同步薄壳在两种上下文中均为**阻塞**语义；需要非阻塞的调用方 SHALL 使用异步入口。

#### Scenario: 异步调用入口
- **GIVEN** 内核 loop 运行于事件循环中，需并发调用多个大模型
- **WHEN** 经 acompletion / astream / aembedding 发起请求
- **THEN** 调用不阻塞事件循环，返回 awaitable / 异步迭代器，多个调用可并发执行

#### Scenario: 同步薄壳等价
- **GIVEN** 调用方处于同步上下文（无运行事件循环），或处于运行中事件循环内
- **WHEN** 调用 completion / stream / embedding 同步入口
- **THEN** 语义与对应异步入口一致，内部经事件循环桥接完成调用；两种上下文均不抛
  `asyncio.run()` 嵌套错误，调用方无需改动、无需感知事件循环

#### Scenario: 运行中事件循环内的同步薄壳
- **GIVEN** 调用方已在运行中的事件循环内（如记忆检索在事件循环线程上同步执行）
- **WHEN** 调用 completion / stream / embedding
- **THEN** 异步实现在一次性工作线程的新事件循环中执行并等待结果返回；
  不产生 `RuntimeWarning: coroutine ... was never awaited`，异常按异步入口同一口径透传

#### Scenario: 真并发执行
- **GIVEN** 多个相互独立的模型调用
- **WHEN** 经异步入口并发发起
- **THEN** 各调用真并发执行（非串行阻塞），总耗时约等于最慢单个调用而非各调用耗时之和
