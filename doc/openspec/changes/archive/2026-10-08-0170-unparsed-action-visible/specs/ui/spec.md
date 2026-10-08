# ui 规格 delta：unparsed-action-visible

## ADDED Requirements

### Requirement: TUI 折叠呈现未能解析的模型原始输出

单轮以**推理产出不可解析**收尾（该轮 `LoopResult.failed` 为真且携带非空 `raw_output`）时，TUI
SHALL 在时间线挂**一个缺省收起**的步骤块呈现该原始产出（标题表明「未能解析」），操作者点击标题
SHALL 可展开查看；SHALL NOT 把该原始产出并入助手回复正文。原始产出 SHALL NOT 写入转录 / 记忆 / 笔记
（该约束由循环侧保证，TUI 只呈现）。该轮未携带 `raw_output`（正常轮次、或形态外失败）时，
TUI SHALL NOT 新增任何块 —— 事件面与既有行为逐字一致。

#### Scenario: 不可解析收尾折叠呈现原始产出

- **GIVEN** 一轮以推理产出不可解析收尾，且 `LoopResult.raw_output` 非空
- **WHEN** TUI 消费该轮事件
- **THEN** 时间线新增**一个缺省收起**的步骤块，展开后其正文含该原始产出
- **AND** 助手回复正文 SHALL 只含可读提示（不含原始产出）

#### Scenario: 无原始产出的轮次零新增

- **GIVEN** 一轮正常收尾（`LoopResult.raw_output` 为空）
- **WHEN** TUI 消费该轮事件
- **THEN** SHALL NOT 呈现该折叠块（时间线与既有行为逐字一致）
