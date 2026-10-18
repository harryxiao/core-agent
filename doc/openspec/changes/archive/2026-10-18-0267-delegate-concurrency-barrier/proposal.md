# Proposal 0267 — 委托动作并发判级修正

## Why

`_is_concurrent_safe` 仅按 coeffect 词元判定只读。`tools.delegate` 声明的 coeffect 是
`agent:delegate`，不含 `write` / `spawn` / `outbound`，因此同一 `ActionGroup` 内的多个
delegate 调用被判为「只读」并并发执行。但子 Agent 可写文件、可执行命令 —— 这破坏了
「写动作是串行屏障、保证写序与撤销快照序」的承诺，且回滚只覆盖父 loop 的 `EffectTracker`，
并发子 Agent 的写入无法按序撤销。

## What Changes

- 并发判定的 deny 词元增加 `delegate`：coeffect 含该词元（如 `agent:delegate`）的工具视为
  **有副作用**，串行执行并作为并发批次之间的屏障。
- 规格 `loop` MODIFIED「单次推理多工具动作」：只读并发条件补 `delegate` 词元，并新增
  「委托动作作为屏障」场景。

## Impact

- `src/core/loop/default.py`（`_CONCURRENT_DENY_TOKENS`）。
- 测试：`tests/test_concurrent_group_tools.py` 新增委托串行用例。
- 文档：`doc/02-modules/loop.md`、`doc/04-testing/test-cases.md`、ADR / 台账。

## 不做（明确边界）

- 不把 `reversible=False` 直接作为并发禁用条件：既有只读测试工具常声明 `reversible=False`
  （可逆性表示「能否撤销」而非「是否只读」），该口径会误伤只读并发。
- 不改变子 Agent 内部工具的并发语义（仍由各自 loop 的同一判定约束）。
