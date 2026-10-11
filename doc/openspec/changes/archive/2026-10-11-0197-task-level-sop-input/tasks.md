# Tasks 0197 — SOP 提炼新增任务级过程输入

## 1. 规格（spec-first）

- [x] `specs/skills/spec.md`：MODIFIED「SOP 提炼（skill extraction）」（+「任务级过程输入」bullet
      + 2 Scenario），既有 7 Scenario 标题零丢失
- [x] ADR-0187（`doc/01-architecture/adr.md`）

## 2. 测试先行（红）

- [x] `test_skills.py`：任务级 `observe` 达阈值入库，`task_types` 含 `task::…` 组键（红：变更前无
      `namespace` 参数 / 无任务级入口）
- [x] `test_skills.py`：任务级与单轮样本**不混组**（同库已有词法相近单轮技能 ⇒ 任务级产物
      `skill_id` 与其**不同**）
- [x] `test_composition.py` / `test_orchestration*.py`：`_steps_lookup` **零效应**（读取不强化
      `reuse_count`、不落盘）
- [x] 组键前缀化确定性（`namespace` 非空 ⇒ `task::…`；缺省 `""` ⇒ 逐字不变）

## 3. 实现（绿）

- [x] `skills/sop.py`：`__init__` + `namespace` kwarg；`_group_key` 最终键前缀化
- [x] `runtime.py`：`_steps_lookup(backend)` + `compose_task_steps(plan, outcomes, lookup)` +
      第二个 `SopExtractor`（`sop-task-samples.json` / `namespace="task"`）+ `_finalize` 接线

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] `openspec validate 2026-10-11-0197-task-level-sop-input`
- [x] 手工归档（delta 合 canonical，断言 0 行丢失 / 0 Scenario 标题丢失）
- [x] `doc/04-testing/test-cases.md` 新 TC 节 + 基线 bump；台账 E134（`known-risk.md` §1）+
      `doc/02-modules/skills.md` / `doc/03-interfaces/skills-interface.md` 对应面
- [x] 单次提交 `feat(skills): …`
