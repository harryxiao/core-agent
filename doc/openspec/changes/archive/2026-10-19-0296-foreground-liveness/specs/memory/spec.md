# memory — 压实的协作式截止与单飞（change 0296）

## ADDED Requirements

### Requirement: 压实的协作式截止与单飞

`MemoryStore.compact` SHALL 接受**可选**的关键字参数 `deadline`（`None` ⇒ 不设截止；数值取
`time.monotonic()` 语义），并 SHALL 在**每次模型调用之前**检查该截止时间：

- 打分（逐条目）、会话摘要（逐会话）、关键事实 / 关系 / 情景归纳（逐会话）之前均 SHALL 检查；
- 已越过截止 ⇒ SHALL 停止发起后续模型调用，经 `warnings.warn` 留痕（只报会话键/阶段，
  SHALL NOT 回显摘要或事件正文），SHALL NOT 提交新的摘要条目、SHALL NOT 迁移材料条目；
- 截止前已完成的会话写回 SHALL 保留（渐进式），其可逆效应与 trace 口径不变；
- 截止 SHALL NOT 抛出异常（与既有「压实失败降级」同向）。

同一 `MemoryStore` 实例上的压实 SHALL **single-flight**：当已有压实正在执行时，新的
`compact` 调用 SHALL **非阻塞跳过**——不发起任何模型调用、返回 `None`，并经 `warnings.warn`
留痕（只报「已在运行」，不含正文）。该跳过 SHALL NOT 排队、SHALL NOT 阻塞调用方。

`deadline` 缺省为 `None` 时，压实行为 SHALL 与引入前**逐字一致**（除 single-flight 外）。

#### Scenario: 截止已过为零调用

- **GIVEN** 注入摘要器与打分器，且 `deadline` 早于当前时钟
- **WHEN** 调用 `compact`
- **THEN** 摘要器与打分器 SHALL NOT 被调用，且不写入摘要条目

#### Scenario: 截止在两次调用之间生效

- **GIVEN** 打分器每次调用推进注入的时钟，`deadline` 位于第 1、2 次调用之间
- **WHEN** 压实打分多条条目
- **THEN** 第 1 次调用执行，第 2 次及之后 SHALL NOT 执行

#### Scenario: 截止后不提交半成品摘要

- **GIVEN** 会话摘要调用返回后已越过截止
- **WHEN** 压实继续处理该会话的派生抽取
- **THEN** 关键事实 / 关系 / 情景归纳 SHALL NOT 被调用；未提交的摘要 SHALL NOT 落库

#### Scenario: 并发压实非阻塞跳过

- **GIVEN** 一次压实正在执行（摘要器阻塞在可控事件上）
- **WHEN** 另一线程调用 `compact`
- **THEN** 第二次调用 SHALL 立即返回 `None`，且不产生额外的模型调用；第一次不受影响

#### Scenario: 未注入截止时行为逐字一致

- **GIVEN** 未传 `deadline`，且没有并发压实
- **WHEN** 调用 `compact`
- **THEN** 打分 / 摘要 / 派生抽取的调用序与产物与引入前逐字一致
