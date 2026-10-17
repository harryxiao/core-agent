# Tasks 0253 — 压实/抽取成本可观测

## 1. 规格

- [x] 1.1 `observability` spec delta：MODIFIED「全链路日志」，补成本事件条款（事件 / payload /
  计时口径 / 脱敏边界）+ 3 Scenario，既有 Scenario 逐字保留。

## 2. 红测试（先写）

- [x] 2.1 `tests/test_loop_cost_observability.py`：
      - 一次节拍 ⇒ 一条 `maintenance` 事件，含总耗时与三步分步耗时
      - 未到节拍间隔 ⇒ 不产事件（与维护同一闸门）
      - 会话压实失败 ⇒ `maintenance_failed` 带 `step`，其余步骤与成本事件照常
      - 一次压实 ⇒ 一条 `compaction` 事件，含 steps 与 `trigger`
      - 压实 persist 失败 ⇒ `step=persist`，记忆两步与成本事件照常
      - 预算降级触发 ⇒ `trigger=budget_retry`

## 3. 实现

- [x] 3.1 `_maintain`：分步 `perf_counter` 计时，末尾发 `maintenance` 事件；失败 payload 增 `step`。
- [x] 3.2 `_compact`：增关键字形参 `trigger`（缺省 `threshold`），分步计时并发 `compaction` 事件。
- [x] 3.3 `_budget_retry`：传 `trigger="budget_retry"`。

## 4. 验证

- [x] 4.1 探针：摘 `maintenance` 事件 ⇒ 3 红；摘 `compaction` 事件 ⇒ 3 红；硬编码 trigger ⇒ 2 红；
      摘失败步骤 `step` ⇒ 1 红；复原 md5 一致。
- [x] 4.2 四门禁：`.venv/bin/ruff check src tests`、`.venv/bin/ruff format --check src tests`、
      `/home/harry/.praisonai/venv/bin/pyright`、`.venv/bin/pytest -q`。
- [x] 4.3 `openspec validate 2026-10-17-0253-compaction-cost-observability --strict` → 归档。

## 5. 文档与收口

- [x] 5.1 ADR-0243；`coding-plan/known-risk.md` E189 + §3 ADR-0243 行。
- [x] 5.2 `doc/04-testing/test-cases.md` §165；`doc/02-modules/loop.md` 成本面；
      `doc/03-interfaces/observability-interface.md` 事件表更新。
- [x] 5.3 单次提交 `feat(observability): ... change 0253 / ADR-0243 / 台账 E189`；更新记忆。
