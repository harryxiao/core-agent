# Tasks 0278 — 未完成任务自动续跑

> 验证目标：默认关时启动扫描逐字不变；开启后未完成任务被重建并续跑（done/turn/坏计划跳过）；
> 自动尝试跨进程有界（3 次，60s 指数退避至 3600s）；`--resume-all` 显式执行。

## 1. 规格与测试先行

- [x] 1.1 `specs/orchestration/spec.md`：ADDED「未完成任务自动续跑」。
- [x] 1.2 `specs/configuration/spec.md`：MODIFIED 编排配置键（新增 auto_resume）。
- [x] 1.3 `specs/durability/spec.md`：MODIFIED 崩溃恢复（显式 opt-in 例外）。
- [x] 1.4 新 `tests/test_auto_resume.py`；`tests/test_entry.py` 补 `--resume-all` / 自动续跑接线。

## 2. 实现

- [x] 2.1 `orchestration/auto_resume.py`：有界退避状态（原子写、损坏容忍）。
- [x] 2.2 `orchestration/models.py`：`TaskResume` 描述符；导出。
- [x] 2.3 `runtime.py`：`_task_resumes` + `Runtime.pending_resumes`。
- [x] 2.4 `configuration/manager.py`：ConfigSpec 三面 + 校验 + 访问器。
- [x] 2.5 `entry.py`：`task --resume-all` 与 auto_resume 启动续跑。

## 3. 验证

- [x] 3.1 四门禁（ruff / format / pyright / pytest）。
- [x] 3.2 反证：① 去掉 done 过滤 ⇒ 已完成任务续跑红；② 去掉退避上限 ⇒ 有界红；
      ③ 默认关仍续跑 ⇒ 默认语义红；复原 `md5sum` 同。
- [x] 3.3 `openspec validate --all` 全绿后归档。

## 4. 文档与登记

- [x] 4.1 ADR-0268（默认关、有界退避、执行位置、局限）。
- [x] 4.2 台账 E214；`doc/04-testing/test-cases.md` §190。
- [x] 4.3 `doc/02-modules/orchestration.md`、`doc/03-interfaces/configuration-interface.md`。
- [x] 4.4 单次提交 `feat(orchestration): ...` + Co-Authored-By。
