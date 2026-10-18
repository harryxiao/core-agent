## MODIFIED Requirements

### Requirement: 异步工具调用
系统 SHALL 提供异步工具调用入口 ainvoke，与同步 invoke 共用统一请求 / 响应模型与 schema / coeffect 校验链路；ainvoke 支持事件循环内非阻塞调用与真并发，invoke 保留为薄壳（thin wrapper），内部经事件循环桥接调用对应异步实现，调用方无需感知事件循环、零改动。

- **同步处理器卸载**：同步（非协程）handler SHALL 经 `asyncio.to_thread` 在工作线程执行，
  SHALL NOT 在事件循环线程内直接调用而阻塞其余任务；协程 handler SHALL 在事件循环上直接 await。
- **超时语义**：外层 `asyncio.wait_for` 超时 SHALL 归一为 `TIMEOUT`；工作线程不可强制终止
  （Python 线程限制）—— 超时停止等待后线程可能继续运行至返回，属已知局限。

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

#### Scenario: 同步处理器不阻塞事件循环
- **GIVEN** 一个同步 handler 正在执行耗时操作，事件循环上另有周期任务
- **WHEN** 经 ainvoke 调用该工具
- **THEN** 周期任务在 handler 执行期间继续推进（事件循环未被阻塞）

#### Scenario: 同步处理器并发
- **GIVEN** 两个同步 handler 各自耗时 T，经 ainvoke 并发发起
- **WHEN** 二者相互独立
- **THEN** 总耗时约等于 T（工作线程重叠执行），而非 2T
