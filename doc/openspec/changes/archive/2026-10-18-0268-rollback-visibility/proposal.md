# Proposal 0268 — 失败回滚可见性

## Why

`DefaultLoop` 在任一动作失败时调用 `self.rollback(trace_id)`，按 trace 逆序撤销**本轮全部**
已记录效应。但 `ToolProvider.rollback` 返回的 `RollbackReport` 被直接丢弃：
模型只看到失败动作的 `error`，不知道**先前成功的写入已被撤销**；运维侧也没有
`trace_rolled_back` 遥测。规格「单轮回滚」已写明「并写遥测」，实现缺失。

## What Changes

- **回滚仍按 trace 整轮回滚**（保持「失败轮回到轮开始前状态」语义；不缩窄到失败动作自身）。
- `DefaultLoop.rollback(trace_id)` 返回 `RollbackReport`；提交循环捕获并：
  - 当有撤销 / 撤销失败时产出 `trace_rolled_back` 遥测，载荷 `reverted` / `undo_failed` 计数；
  - 把同一计数附加到该失败动作回灌给模型的 tool observation（`rollback.reverted` /
    `rollback.undo_failed`），使模型知道先前写入已回退、以及是否有撤销失败遗留。
- 无效应可撤销时：不产出事件、observation 键集与既有逐字一致（避免噪声）。

## Impact

- `src/core/loop/default.py`（`rollback` 返回值、提交循环、`_record_observation`）。
- 测试：新增 `tests/test_rollback_visibility.py`。
- 文档：`doc/02-modules/loop.md`、`doc/04-testing/test-cases.md`、ADR / 台账。

## 不做（明确边界）

- 不改为「只回滚失败动作自身的效应」：效应记录只有 trace 粒度，且整轮回滚是既有承诺；
  缩窄会留下半个轮次的写入。
- 不把 `EffectId` / undo 闭包 / 错误正文写进 observation 或遥测（只给计数）。
- 不新增 `LoopEvent` 类型（事件流七类契约不变）；遥测走 `Tracer`。
