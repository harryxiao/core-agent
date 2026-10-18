# Tasks 0275 — 记忆检索规模基准（1 万条，PA-09 方案 B）

## 1. 规格

- [x] 1.1 `memory` delta：ADDED「检索规模离线基准（1 万条）」（3 scenarios）。

## 2. 红测试（先写）

- [x] 2.1 `tests/test_memory_scale_benchmark.py`：1 万条固定语料 + 20 查询；
      recall@5 ≥ 0.9、MRR@5 ≥ 0.7；打印延迟中位/p95/max。
- [x] 2.2 规模锚：`len(store.audit(None)) == 10_000`。
- [x] 2.3 延迟护栏：p95 < 5000ms（产品 100ms 目标只报告、不设门禁）。
- [x] 2.4 语料确定性：两次独立生成逐条一致。

## 3. 实现

- [x] 3.1 仅测试与文档；零 `src/` 改动（延迟缺口另立 change 修复）。

## 4. 验证

- [x] 4.1 反证：临时反转排序 ⇒ recall/MRR 红；复原后全绿。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR-0265；`coding-plan/known-risk.md` 台账 E211 ＋ §3 局限行（含 100ms 未达标）。
- [x] 5.2 `doc/04-testing/test-cases.md` §187；`doc/02-modules/memory.md` 补规模基准。
- [x] 5.3 `coding-plan/Pending-Arbitration.md`：PA-09 方案 B 标已闭，C/D/E 仍开放。
- [x] 5.4 单次提交 `feat(memory): ... change 0275 / ADR-0265 / 台账 E211`；更新记忆。
