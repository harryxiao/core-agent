# tasks — 自动课程（目标生成与调度，change 0084 / 账本 E5）

## 1. 规格先行
- [x] 1.1 `specs/evolution/spec.md` delta：ADDED「自动课程（目标生成与调度）」+ MODIFIED「对比诊断」「冷路径驱动」
- [x] 1.2 `openspec validate 0084-curriculum-goal-selection` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_evolution_curriculum.py`（新）：失败强度定序 / 已处理降权 / 降权不改证据强度 / 先验不压证据 / 空信号空议程 / 预算上限 / 确定性
- [x] 2.2 `tests/test_evolution.py`：诊断先验解并列（无先验仍转人工）+ `run_cycle` 显式目标直接采用
- [x] 2.3 `tests/test_entry.py`：`evolve run --goal` 目标透传 + 回显
- [x] 2.4 红证：实现前 2.1 / 2.2 / 2.3 失败

## 3. 实现（绿）
- [x] 3.1 `src/core/evolution/curriculum.py`（新）：`EvolutionGoal` + `CurriculumPlanner`（`plan(explicit=…)` 产出 directive 目标）
- [x] 3.2 `src/core/evolution/diagnoser.py`：`diagnose(traces, *, prior=None)`
- [x] 3.3 `src/core/evolution/engine.py`：`run_cycle(traces, *, goals=None)`（directive 直采 / 否则议程作先验）
- [x] 3.4 `src/core/evolution/worker.py`：`planner` 注入（缺省自建）+ `maybe_run(*, goal=None)` 组装议程
- [x] 3.5 `src/core/evolution/__init__.py`：导出 `CurriculumPlanner` / `EvolutionGoal`
- [x] 3.6 `src/core/entry.py`：`evolve run [--goal]` + 结局行回显目标
- [x] 3.7 绿证：四门全绿（基线 + 新增）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/evolution-interface.md`：诊断先验入参 + 课程（目标选择层）小节 + `evolve run --goal`
- [x] 4.2 `doc/02-modules/evolution.md`：§4 触发时机补课程（自动议程 / 显式目标）
- [x] 4.3 `doc/01-architecture/adr.md`：ADR-0079 + 变更追踪行
- [x] 4.4 `doc/04-testing/test-cases.md`：TC-EVO 课程行（议程定序 / 先验不压证据 / `--goal`）
- [x] 4.5 `doc/00-product/user-guide.md`：`evolve run --goal` 用法

## 5. 收口
- [x] 5.1 `coding-plan/phase-19.md`：§1 E5 行 → ✅ 已关闭（change 0084）；§0 / §9 同步
- [x] 5.2 `coding-plan/README.md`：状态行 + 下一步同步
- [x] 5.3 手动归档（合并 delta + `shutil.move`）+ `openspec validate --all` 全绿
- [x] 5.4 记忆更新 + 提交
