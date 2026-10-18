# Tasks 0285 — 续跑批次单实例锁与 cron 运维闭环

> 验证目标：并发 `--resume-all` 只有一个扫描并执行；锁覆盖整个批次；busy 显式入口退出 0、
> 锁不可用退出 1；自动模式 busy 仍执行新任务；无冲突路径行为逐字不变；四门禁与
> `openspec validate --all` 全绿。

## 1. 规格与测试先行

- [x] 1.1 spec delta：orchestration ADDED「续跑批次单实例互斥」（5 场景）。
- [x] 1.2 `tests/test_auto_resume.py` 追加锁助手与 CLI 用例（先红）。

## 2. 锁助手

- [x] 2.1 `state_files.py`：`LockOutcome`、`_try_lock_fd`（`LOCK_NB` / `LK_NBLCK`）。
- [x] 2.2 `try_exclusive_file_lock`：fail-closed 三态、0600、释放不删文件；模块 docstring 区分两种锁。

## 3. 入口接线

- [x] 3.1 `entry.py` import 助手；`_run_auto_resume` 取锁 + 三态分流。
- [x] 3.2 原批次逻辑拆入 `_run_auto_resume_locked`（逐字不动，满足嵌套门禁）。
- [x] 3.3 `tests/test_unattended.py` 直接调用点补 `CORE_STATE_DIR` 隔离。

## 4. 运维手册

- [x] 4.1 新 `doc/05-development/unattended-ops.md`（cron 前提/示例/退出码/护栏/止血/局限）。
- [x] 4.2 `doc/README.md` 05-development 树补条目；user-guide 与 development-guide 指向。

## 5. 台账与对齐

- [x] 5.1 ADR-0275（决策/退出码/被拒方案/局限）。
- [x] 5.2 known-risk E221 + §3 索引；test-cases §197。
- [x] 5.3 orchestration 模块/接口文档；alignment §3.8 与 P1 行、证据索引。

## 6. 验证与收尾

- [x] 6.1 四门禁（ruff check / ruff format --check / pyright / pytest）。
- [x] 6.2 反证 3/3（cp 复原 + md5sum）。
- [x] 6.3 `openspec validate --all` 31/0 后归档。
- [x] 6.4 单次提交 `feat(orchestration): ...` + Co-Authored-By。
