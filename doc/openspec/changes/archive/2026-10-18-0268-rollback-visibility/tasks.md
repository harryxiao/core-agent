# Tasks 0268 — 失败回滚可见性

## 1. 规格

- [x] 1.1 `loop` delta：ADDED「失败回滚可见性」（整轮回滚 + 遥测 + 观察回灌）。

## 2. 红测试（先写）

- [x] 2.1 先成功写入、后动作失败：undo 被调用，observation 带 `rollback` 计数，
      trace 记 `trace_rolled_back`。
- [x] 2.2 无效应可撤销的失败：observation / 遥测与既有逐字一致（无 `rollback` 键、无事件）。
- [x] 2.3 undo 抛错：observation 与遥测均报 `undo_failed=1`，账目留隔离。

## 3. 实现

- [x] 3.1 `DefaultLoop.rollback` 返回 `RollbackReport | None`。
- [x] 3.2 提交循环捕获报告，非空时记 `trace_rolled_back` 遥测。
- [x] 3.3 `_record_observation` 附加可选 `rollback` 计数。

## 4. 验证

- [x] 4.1 反证：丢弃报告（恢复旧 `rollback` 返回 None）⇒ 2.1/2.3 红；摘 observation 注入
      ⇒ 2.1 红；复原 `md5sum` 同。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR；`coding-plan/known-risk.md` 台账条目。
- [x] 5.2 `doc/04-testing/test-cases.md`；`doc/02-modules/loop.md`。
- [x] 5.3 单次提交 `feat(loop): ... change 0268 / ADR-0258 / 台账 E204`；更新记忆。
