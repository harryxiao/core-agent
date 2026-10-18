## ADDED Requirements

### Requirement: 失败回滚可见性

动作失败触发回滚时，系统 SHALL 让**模型与运维侧**都能看到回滚结果，SHALL NOT 静默丢弃
`RollbackReport`。

- 回滚范围 SHALL 保持**按 trace 整轮**（逆序撤销该轮已记录的全部可逆效应），SHALL NOT 缩窄为
  只撤销失败动作自身的效应。
- 当回滚**确有撤销或撤销失败**（`reverted` 或 `undo_failed` 非空）时，循环 SHALL 产出
  `kind="trace_rolled_back"` 遥测，载荷键 SHALL 恰为 `reverted` / `undo_failed`（非负计数）；
  SHALL NOT 含 `EffectId`、路径、参数、错误正文或其他正文。
- 失败动作回灌给模型的 tool observation SHALL 在**非空**回滚时附加
  `rollback: {"reverted": <count>, "undo_failed": <count>}`；空回滚时 observation 的键集与
  既有逐字一致（SHALL NOT 出现空的 `rollback` 键）。
- 回滚 SHALL 在观测回灌**之前**完成：模型看到失败结果时，先前成功写入已按逆序撤销（或已记录
  撤销失败）。
- 撤销失败的效应 SHALL 留在账目隔离（既有 QUARANTINE 语义），SHALL NOT 自动重试或删除。
- 终止动作不产生 observation（既有语义），但其失败触发的回滚 SHALL 照常产出遥测。
- 事件流七类 `LoopEvent` 契约 SHALL 不变（本能力只走 `Tracer`）。

#### Scenario: 先前写入被撤销且模型可见
- **GIVEN** 本轮先有一个成功的可逆写动作，随后另一个动作失败
- **WHEN** 循环执行失败回滚
- **THEN** 该写动作的 undo 被调用；失败动作的 tool observation 含
  `rollback.reverted=1`、`rollback.undo_failed=0`；trace 记 `trace_rolled_back`（同计数）

#### Scenario: 无效应可撤销时保持逐字一致
- **GIVEN** 失败动作之前本轮没有任何已记录效应
- **WHEN** 循环执行失败回滚
- **THEN** tool observation 不含 `rollback` 键，且不产出 `trace_rolled_back` 遥测

#### Scenario: 撤销失败被如实上报
- **GIVEN** 本轮成功写入的效应 undo 抛错，随后另一个动作失败
- **WHEN** 循环执行失败回滚
- **THEN** observation 与 `trace_rolled_back` 均报 `undo_failed=1`；该效应仍留在账目隔离
