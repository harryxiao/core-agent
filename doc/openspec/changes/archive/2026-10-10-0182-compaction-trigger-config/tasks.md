# 任务 — 压实触发的诚实化与配置注入（change 0182）

## 规格与设计

- [x] `specs/context/spec.md` delta：`上下文自动压实` 增触发判据 + 每轮至多一次 + 2 Scenario；
      `三层窗口比例分配` 括注改口
- [x] `specs/configuration/spec.md` delta：`循环预算配置` 增第四键 + 校验 + 1 Scenario
- [x] `proposal.md` / `design.md`（D1–D5 + I1–I7 + 被改写条款说明）

## 先红测试

- [x] `tests/test_context_compaction.py`：`_DEFAULT_ROUNDS` → `_DEFAULT_STEPS = 6`；
      `test_default_round_threshold_boundary` → `test_default_step_threshold_boundary`；
      新增 `test_step_threshold_injectable`、`test_config_default_matches_compactor_default`
- [x] `tests/test_context_compaction.py`：新增 `test_loop_compacts_at_most_once_per_turn`（红）
- [x] `tests/test_context_compaction.py`：新增 `test_loop_step_threshold_triggers_before_limit`（红）
- [x] `tests/test_context.py::test_compactor_should_compact_threshold` 口径改「工具步数」+ 新增步数边界断言
- [x] `tests/test_memory_config.py` 或新 `tests/test_loop_config_compact_steps.py`：
      `compact_steps()` 缺省 `6` / 三面解析 / 非法阻断
- [x] 调用点更名：`tests/test_notes_loop.py:458`、`tests/test_loop_offload_threads.py:186,207`、
      `tests/test_loop.py:586,602,629,647`

## 实现

- [x] `compactor.py`：`_STEP_THRESHOLD = 6`、`step_threshold`、`should_compact(steps, …)`
- [x] `loop/default.py`：`astream()` 局部标记 `compacted` + 触发点短路；`_should_compact` 文案改「工具步数」
- [x] `configuration/manager.py`：`_DEFAULT_COMPACT_STEPS`、ConfigSpec、`compact_steps()`、`_loop_errors` 校验
- [x] `runtime.py`：`ContextCompactor(memory=memory, step_threshold=config.compact_steps())`

## 门禁

- [x] `.venv/bin/ruff check src tests`
- [x] `.venv/bin/ruff format --check src tests`
- [x] `/home/harry/.praisonai/venv/bin/pyright`（0/0/0）
- [x] `.venv/bin/pytest -q`（基线 **2146**；记录增量）

## 收口

- [x] `openspec validate 2026-10-10-0182-compaction-trigger-config`（全目录名）
- [x] 手工归档：delta 合 canonical（断言 0 canonical 行丢失 / 0 Scenario 标题丢失）⇒ `mv` 进 archive/
- [x] `doc/01-architecture/adr.md`：ADR-0173 + 追踪行
- [x] `doc/02-modules/context.md`（压实触发口径）、`doc/02-modules/configuration.md`（新键）
- [x] `doc/03-interfaces/context-interface.md:108`（`should_compact` 签名与语义）
- [x] `doc/04-testing/test-cases.md`：新 TC 节 + 基线 bump
- [x] `coding-plan/known-risk.md`：§1 E119 行（关 E96 余项）+ §3 ADR-0173 行
- [x] 记忆：`MEMORY.md` + `coding-plan-leftover-walkthrough.md`
- [x] 单次提交：`feat(context): …（change 0182 / ADR-0173 / 台账 E119）`
