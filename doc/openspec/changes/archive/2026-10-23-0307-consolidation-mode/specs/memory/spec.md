# Spec Delta — memory（0307 巩固的可关闭性与水位语义）

## ADDED Requirements

### Requirement: 巩固的可关闭性

`MemoryStore` SHALL 接受构造参数 `consolidation_enabled`（缺省 `True`）。为 `False` 时
`compact(...)` SHALL 在任何评分、模型调用、写入、迁移与效应记录之前**立即返回 `None`**：
不产会话摘要、不抽关键事实 / 关系 / 情景归纳、不把原条目迁 L4，原始 L2 情景记录保持不变。
`consolidation_enabled=False` SHALL NOT 影响 `forget()`（自然衰减归档）与会话滑窗中期摘要
（`summarize_slice`）。

缺省 `True` 时 `compact(...)` 的行为 SHALL 与变更前逐字一致。

巩固的持久队列与水位 SHALL 由 L2 未迁移的 episodic 条目本身承载：成功提交摘要的批次迁 L4
（水位前进），低于价值门、空摘要、截止越界或摘要器失败时条目不迁移（水位不前进，下次重试）。
系统 SHALL NOT 为此引入独立的任务队列文件或第二权威存储。

#### Scenario: 关闭巩固时零副作用

- **GIVEN** 一个 `consolidation_enabled=False` 的存储，装配了评分器、摘要器与三个抽取器
- **WHEN** 写入一条 L2 episodic 条目后调用 `compact()`
- **THEN** 返回 `None`；评分器与全部模型钩子均未被调用；条目仍为 L2、无新增条目、无可撤销效应

#### Scenario: 缺省开启时行为不变

- **GIVEN** 未指定 `consolidation_enabled`
- **WHEN** 对同一批 L2 episodic 条目调用 `compact()`
- **THEN** 正常产出会话摘要并迁移原条目（与变更前一致）

#### Scenario: 关闭巩固不影响遗忘

- **GIVEN** `consolidation_enabled=False`，存在一条衰减分低于阈值的 L2 episodic 条目
- **WHEN** 调用 `forget()`
- **THEN** 该条目仍被归档到 L4（遗忘不属于知识固化）

#### Scenario: 失败不推进水位

- **GIVEN** 一条 L2 episodic 条目与一个抛错的摘要器
- **WHEN** `compact()` 抛错，随后换用正常摘要器重试
- **THEN** 首次失败后条目仍在 L2；重试成功并迁移（队列在 L2，非进程内状态）
