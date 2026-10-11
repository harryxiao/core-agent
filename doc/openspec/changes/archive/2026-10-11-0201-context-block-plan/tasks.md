# Tasks 0201 — 上下文区块配比（五区块 / 80-20 安全线）

## 1. 规格（spec-first）

- [ ] `specs/context/spec.md`：ADDED「上下文区块配比（五区块 / 80-20 安全线）」+ 5 Scenario
- [ ] ADR-0191（`doc/01-architecture/adr.md`）+ 「变更追踪」表行
- [ ] **既有规格零改动**（`三层窗口比例分配` / `动态上下文构建` 逐字保留）

## 2. 测试先行（红）

- [ ] `tests/test_context_blocks.py`：关 ⇒ `plan_blocks(B, enabled=False) is None`
- [ ] 启用 ⇒ 四份额 = `0.20/0.15/0.30/0.15` 向下取整、缓冲 `≥ 0.20 × B`
- [ ] 启用 ⇒ 五块之和 `≤ B`
- [ ] `0` / 负预算 ⇒ `None`（**不**是全零）
- [ ] 配额对总预算**单调不减**
- [ ] **逐字锚**：桩装配器捕获 `build(budget=)`，`block_plan` 关 ⇒ 捕获 `2048`（红：断言 `== 派生值`）
- [ ] 启用 + `ctx.token_budget=B` ⇒ 捕获 `plan_blocks(B, enabled=True).memory_tokens`

## 3. 实现（绿）

- [ ] `src/core/context/blocks.py`（新）：`BlockPlan` + 五个份额常量 + `plan_blocks`
- [ ] `src/core/context/__init__.py`：导出 `BlockPlan` / `plan_blocks`
- [ ] `src/core/loop/protocol.py`：`LoopContext.token_budget: int = 0`
- [ ] `src/core/loop/default.py`：`perceive()` 置 `ctx.token_budget = self._token_budget`
- [ ] `src/core/loop/planner.py`：构造参 `block_plan: bool = False` + `_system_prompt` 改派
- [ ] `src/core/configuration/manager.py`：`_FEATURE` 归一访问器 `block_plan()` + ConfigSpec 行
      （+ `_loop_errors` 校验）
- [ ] `src/core/runtime.py`：`config.block_plan()` 注入四个 planner

## 4. 门禁与收口

- [ ] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
      （2255 → 2262）
- [ ] **反证**：把 `LLMPlanner(block_plan=…)` 缺省翻成 `True` ⇒ 逐字锚 `2048` 转红；复原 ⇒ 绿
- [ ] `openspec validate 2026-10-11-0201-context-block-plan`
- [ ] 手工归档（ADDED 追加；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失）
- [ ] `doc/04-testing/test-cases.md` §114 + 基线 bump；台账 E138（`known-risk.md` §1）+
      §3 ADR-0191 行；`doc/02-modules/context.md` 增一节
- [ ] 单次提交 `feat(context): …`
