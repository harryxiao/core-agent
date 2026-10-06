# Plugin Registry Specification Delta

## ADDED Requirements

### Requirement: 可逆效应追踪（清账与幂等）

系统 SHALL 以效应账（`EffectTracker`）承载「一切副作用可逆」：`record` 记账并返回句柄（`EffectId`）；`rollback(trace_id)` 对该轮效应**逆序**撤销，`trace_id=None` 则全局回滚；结果经 `RollbackReport` 汇总为「已撤销」与「撤销失败」两类。

回滚 SHALL **清账**：撤销**成功**的效应 SHALL 随即出账（其 `EffectId` SHALL 从账中移除、所属 trace 的映射 SHALL 同步清理、trace 键清空即删除），使同一 trace **重复回滚 SHALL NOT 二次撤销**同一效应；账目 SHALL NOT 无界增长。

**不可逆**效应（`reversible=False`）SHALL NOT 参与撤销，SHALL 随清账一并出账（既无待撤销项、亦无失败项可隔离）。

撤销**失败**的效应 SHALL **留账隔离**：其 `EffectId` SHALL 仍在账（可见于 `audit`）、并由 `RollbackReport.undo_failed` 报告，SHALL NOT 静默丢弃；单条撤销失败 SHALL NOT 中断其余效应的撤销。

系统 SHALL 提供**显式清账** `clear(trace_id=None)`（trace 级 / 全局）：只移除账目、SHALL NOT 触发任何 undo，供调用方在丢弃一轮效应时不执行撤销。

#### Scenario: 撤销成功后出账且重复回滚不二次撤销

- **GIVEN** 同一 trace 下记录了两条可逆效应
- **WHEN** 对该 trace 回滚两次
- **THEN** 首次按**逆序**各调用一次 undo 且二者均计入「已撤销」；**第二次**回滚的「已撤销」与「撤销失败」均为**空**，且 undo **不再被调用**

#### Scenario: 回滚后账目清空且不越界

- **GIVEN** 同一 trace 下记录了若干可逆效应，另有**其它 trace** 的效应记录
- **WHEN** 对该 trace 回滚
- **THEN** 该 trace 的 `audit` 返回**空列表**，而其它 trace 的账目**逐条不受影响**（trace 级隔离）

#### Scenario: 撤销失败者留账隔离

- **GIVEN** 同一 trace 下一条效应的 undo 抛异常，另一条正常
- **WHEN** 对该 trace 回滚
- **THEN** 失败者出现在「撤销失败」中且**仍在账**（`audit` 仍可查得），正常者出账，且回滚**不抛出**异常

#### Scenario: 显式清账不触发撤销

- **GIVEN** 一条 trace 下尚有未回滚的可逆效应
- **WHEN** 调用 `clear`（trace 级或全局）
- **THEN** 对应账目被移除且**未调用任何 undo**
