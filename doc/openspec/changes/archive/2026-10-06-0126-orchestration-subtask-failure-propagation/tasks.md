# tasks — 子任务失败态传播（假成功收口）（change 0126 / phase-34 E63）

## 1. 规格（先行）
- [x] 1.1 `specs/orchestration/spec.md`：MODIFIED「子任务验收门」——补「执行失败态 fail-closed」+
      「失败态传播（`ok = 验收通过 且 执行未失败`）」口径
- [x] 1.2 同 delta：新增 Scenario「执行失败态不因非空合成回复通过」（保留既有 3 个 Scenario 逐字）
- [x] 1.3 `openspec validate 0126-orchestration-subtask-failure-propagation` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_orchestration.py`：**执行失败 + 非空回复 + 无验收标准**（离线判定本会通过）⇒
      子任务**不**记录完成、`subtask_completed.ok is False`、波次收口 `task_failed`、任务转 RECOVERING
- [x] 2.2 同文件：**执行失败 + 有验收标准**（验收门本会通过）⇒ 仍 **fail-closed**（`ok is False`）
- [x] 2.3 同文件：**回归** —— 正常成功路径 `ok is True` 且 `tracker.completed` 逐字不变
- [x] 2.4 红：2.1 / 2.2 在实现前**必失败**（现状 `ok is True`）

## 3. 实现
- [x] 3.1 `src/core/orchestration/errors.py`：`OrchestrationErrorCode` **追加** `SUBTASK_EXECUTION_FAILED`
- [x] 3.2 `src/core/orchestration/scheduler.py:_run_subtask`：判据合并为 `ok = verify.passed and not
      result.failed`；`subtask_completed` 载荷 `ok` 取该真值；失败态理由记为「执行未达成」（`verify` 本
      失败时保留 `verify.reason`）；`SubtaskOutcome` 失败分支错误码取 `SUBTASK_EXECUTION_FAILED`

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`（须 0/0/0）
- [x] 4.4 `.venv/bin/pytest -q`（基线 1599 passed ⇒ 新增后按实累加）
- [x] 4.5 `openspec validate --all`（归档前后各一次，30 passed / 0 failed）

## 5. 归档
- [x] 5.1 手工合并 delta 进 canonical `doc/openspec/specs/orchestration/spec.md`（对齐既有排版：
      `### Requirement:` 正文紧接、`#### Scenario:` 后不留空行）
- [x] 5.2 目录 `shutil.move` 至 `doc/openspec/changes/archive/2026-10-06-0126-orchestration-subtask-failure-propagation/`

## 6. 文档与账本
- [x] 6.1 `doc/01-architecture/adr.md`：**ADR-0119**（决策：执行失败态并入验收门判据、与 `delegate`
      正解对齐；不新增旁路；新增 `SUBTASK_EXECUTION_FAILED` 码的取舍；已知局限 + 变更追踪表行）
- [x] 6.2 `doc/04-testing/test-cases.md` 增 TC 行
- [x] 6.3 `coding-plan/phase-34.md`：§1 真缺陷表 **E63** 行标「已落地（change `0126` / ADR-0119）」；
      `coding-plan/README.md` 索引同步
- [x] 6.4 记忆：`coding-plan-leftover-walkthrough.md` + `MEMORY.md`

## 7. 提交
- [x] 7.1 单次提交：`fix(orchestration): 子任务失败态传播（假成功收口）（change 0126）`
- [x] 7.2 **不提交**：`config.yaml`、`.claude/settings*.json`（D4 不动）、`coding-plan/phase-3-prompt.md`、
      `AI-SoftwareEngineer-4.md`、`coding-plan/phase-32.md`、`src-tauri/Cargo.lock`、`node_modules/`、
      `frontend/dist/`
