# Tasks 0263 — 压实丢弃与产出的可观测计数

## 1. 规格

- [x] 1.1 `observability` delta：MODIFIED「全链路日志」（`compaction` payload 增五项计数 + 1 scenario）。

## 2. 红测试（先写）

- [x] 2.1 `compaction` payload 含 `messages/conclusions/decisions/open_items/dropped` 且计数正确。
- [x] 2.2 payload 顶层 key 集合恰为 `{trigger, elapsed_ms, steps, messages, conclusions, decisions, open_items, dropped}`。
- [x] 2.3 `compact` 抛异常 ⇒ 五项计数全 0，事件照常产出。
- [x] 2.4 `persist` 失败 ⇒ 计数仍为真实产出（非 0）。

## 3. 实现

- [x] 3.1 `DefaultLoop._compact` 先取 `compact()` 产物再 `persist`，计算五项计数。
- [x] 3.2 既有 `trigger` / `elapsed_ms` / `steps` 与写回 / 终止语义不变。

## 4. 验证

- [x] 4.1 反证：去掉 dropped 计数 / 异常时填非零 / 摘 messages 键 ⇒ 对应用例红；复原后全绿。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR-0253；`coding-plan/known-risk.md` E199 + §3 行。
- [x] 5.2 `doc/04-testing/test-cases.md` §175；`doc/02-modules/loop.md` / `doc/03-interfaces/observability-interface.md` 补计数。
- [x] 5.3 单次提交 `feat(observability): ... change 0263 / ADR-0253 / 台账 E199`；更新记忆。
