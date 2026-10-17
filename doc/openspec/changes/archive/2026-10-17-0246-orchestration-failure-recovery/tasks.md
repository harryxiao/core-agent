# Tasks — 编排失败恢复（change 0246）

## 1. 规格

- [x] 1.1 `orchestration/spec.md` R2「子任务拆解」MODIFIED（重试/重拆/异常归一/空计划 + 6 Scenario）
- [x] 1.2 `orchestration/spec.md` R4「断点续跑」MODIFIED（`Plan.replans` 持久化 + 1 Scenario）
- [x] 1.3 `openspec validate 2026-10-17-0246-orchestration-failure-recovery`

## 2. 红测试

- [x] 2.1 重试第 2 次通过 ⇒ `DONE`，`subtask_started.attempt=2`，`replans=0`
- [x] 2.2 重试仍失败 ⇒ 触发 1 次重拆（`task_replanning` / `plan_ready.replan=1`）
- [x] 2.3 重拆后成功 ⇒ `DONE` 且 `Plan.replans=1`
- [x] 2.4 重试 + 重拆均失败 ⇒ `FAILED`，payload 带 `attempts`/`replans` 与最后原因
- [x] 2.5 执行异常 ⇒ 归一失败并可重试，不裸崩
- [x] 2.6 重拆清空旧完成集/结果，id 复用不误跳过
- [x] 2.7 空计划 ⇒ `FAILED`（不误判 `DONE`）
- [x] 2.8 `Plan.replans` 往返 + 旧检查点缺键回落 0
- [x] 2.9 成功路径事件序列逐字不变（回归）

## 3. 实现

- [x] 3.1 `models.py`：`Plan.replans` + `plan_to_dict`/`plan_from_dict`
- [x] 3.2 `scheduler.py`：恢复回路、重试、重拆、空计划守卫
- [x] 3.3 `scheduler.py`：`_fan_out` 异常归一 guard
- [x] 3.4 `scheduler.py`：事件 `task_retrying`/`task_replanning`、`attempt`/`replan` 字段
- [x] 3.5 `_enter_executing` 增加 `RECOVERING` 分支
- [x] 3.6 接口/模块文档同步

## 4. 门禁与反证

- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`
- [x] 4.4 `.venv/bin/pytest -q`
- [x] 4.5 反证：摘重试分支 ⇒ 2.1 红；摘重拆分支 ⇒ 2.2/2.3 红；
      摘 RECOVERING 分支 ⇒ 2.3 红；复原 md5 同

## 5. 收口

- [x] 5.1 归档到 `doc/openspec/changes/archive/2026-10-17-0246-orchestration-failure-recovery/`
- [x] 5.2 ADR-0234 + 变更追踪表
- [x] 5.3 台账 E181（`coding-plan/known-risk.md`）+ 测试节 §157（`doc/04-testing/test-cases.md`）
- [x] 5.4 接口文档同步（`doc/03-interfaces/orchestration-interface.md` / `doc/02-modules/orchestration.md`）
- [x] 5.5 单次提交（change 0246 / ADR-0234 / 台账 E181）
