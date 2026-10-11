# Tasks 0200 — 压缩轴口径裁决

## 1. 规格（spec-first）

- [ ] `specs/context/spec.md`：ADDED「压缩轴口径（轮 / 步两轴不可互换）」+ 4 Scenario
- [ ] ADR-0190（`doc/01-architecture/adr.md`）+ 「变更追踪」表行
- [ ] **既有规格零改动**（不改 `三层窗口比例分配` / `上下文自动压实`）

## 2. 测试先行（红）

- [ ] `tests/test_axis_units.py`：`should_compact(6, 0, 0) is True` 且 `(5, 0, 0) is False`
      （**零预算** ⇒ 触发只可能来自步轴）
- [ ] `tests/test_axis_units.py`：`LoopContext().rounds == 0`（步计数每轮归零 ⇒ 轮不可表达）
- [ ] `tests/test_axis_units.py`：`plan_window(20, B, tiered=True).short_turns == 10` 且
      `plan_window(40, B, tiered=True).short_turns == 20`（边界随轮等比缩放 ⇒ 轮比率）
- [ ] 先跑一次确认 3 条**全绿**（本 change 零行为改动 ⇒ 是**守护**断言，非 red→green；
      **反证**见 §4：临时改断言输入 ⇒ 转红）

## 3. 实现（绿）

- [ ] **无** —— 本 change 零 `src/` 改动

## 4. 门禁与收口

- [ ] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [ ] **反证**：把守护断言改成传**轮数**（如 `should_compact(6, 0, 0)` → `should_compact(0, 0, 0)`
      或把 `plan_window` 断言换成固定字面边界）⇒ 转红；复原 ⇒ 绿
- [ ] `git diff --stat src/` 为空
- [ ] `openspec validate 2026-10-11-0200-compaction-axis-ruling`
- [ ] 手工归档（delta 合 canonical，断言 0 Requirement 头丢失 / 0 Scenario 标题丢失）
- [ ] `doc/04-testing/test-cases.md` §113 + 基线 bump；台账 E137（`known-risk.md` §1）+
      §3 ADR-0190 行；`doc/02-modules/context.md` 窗口/tier 段落**若含轮步混同表述**则订正
      （否则不动）
- [ ] 单次提交 `test(context): …`
