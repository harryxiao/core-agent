# Orchestration Specification Delta — 任务完成回调卸载（change 0196）

## MODIFIED Requirements

### Requirement: 异步执行单元契约
系统 SHALL 明确并行扇出的执行单元契约：扇出派发的每个执行单元复用 llm-provider 的 acompletion 与 tool-use 的 ainvoke 异步接口，支持事件循环内非阻塞与真并发执行，消除同步串行阻塞；同一波次内无依赖子任务经异步接口并发派发，不再是串行阻塞。

- **收尾回路不阻塞**：任务完成回调（`on_done`）SHALL 经 `asyncio.to_thread` **卸载**至工作线程执行，SHALL NOT 在事件循环上同步阻塞 —— 回调若承载模型调用等重活，SHALL NOT 阻塞流式产出与已派发的并发。该卸载 SHALL NOT 改变回调的**调用时机与次数**（仍在 `DONE` 达成后调用一次）与终态判定。

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

#### Scenario: 完成回调不阻塞事件循环
- **GIVEN** 任务达成 `DONE` 且注入了完成回调（回调内含阻塞工作）
- **WHEN** 编排器触发完成回调
- **THEN** 回调在**工作线程**（非事件循环线程）执行，流式产出不被同步阻塞；回调的调用时机与次数不变（`DONE` 后一次）
