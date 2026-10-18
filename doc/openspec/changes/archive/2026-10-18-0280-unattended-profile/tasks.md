# Tasks 0280 — 无人值守 profile

> 验证目标：四项配置三面齐备、缺省全关闭；auto-approve 允许面按声明 coeffect 全含判定、
> 越界拒绝；整任务超时终止且保留检查点；token 预算耗尽 ⇒ `TASK_TOKEN_BUDGET_EXCEEDED`
> 且不重试不重拆；失败通知 JSONL 脱敏、0600、不改变任务结局。

## 1. 规格与测试先行

- [x] 1.1 spec delta：`configuration` / `permission` / `orchestration` / `loop`。
- [x] 1.2 新 `tests/test_unattended.py`（配置 / 允许面 / 预算 / 超时 / 通知）。

## 2. 配置层

- [x] 2.1 四个 ConfigSpec + 常量（CLI / env / yaml 三面）。
- [x] 2.2 校验：允许面条目形态、`task_timeout` / `task_token_budget` ≥0 整数（布尔非法）、
      `failure_notify_file` 字符串。
- [x] 2.3 访问器：`permission_auto_approve_coeffects` / `orchestration_task_timeout` /
      `orchestration_task_token_budget` / `orchestration_failure_notify_file`。

## 3. 权限允许面

- [x] 3.1 `PermissionModeGate(allowed_coeffects=...)`：auto-approve 分支前置全含检查。
- [x] 3.2 `PermissionGuard(allowed_coeffects=...)` 透传；runtime 注入配置值。

## 4. 整任务护栏

- [x] 4.1 `LoopResult.token_used`（缺省 0）；`DefaultLoop` 以 `ctx.token_used` 填充。
- [x] 4.2 `OrchestrationErrorCode`：`TASK_TIMEOUT` / `TASK_TOKEN_BUDGET_EXCEEDED`。
- [x] 4.3 `TaskScheduler(task_token_budget=...)`：累计、越界失败、禁重试/禁重拆、终态清除；
      runtime 注入。
- [x] 4.4 `entry`：`_run_task_stream`（`wait_for`）、`_task` 与 `_run_auto_resume` 超时分支
      （退出码 / 告警 / 检查点保留）。

## 5. 失败通知 sink

- [x] 5.1 `entry._notify_failure`：JSONL 追加、脱敏、有界、0600 创建、写失败告警。
- [x] 5.2 `_stream_task` 在 `task_failed`（非取消）时调用；超时分支显式调用。

## 6. 验证

- [x] 6.1 四门禁（ruff check / ruff format --check / pyright / pytest）。
- [x] 6.2 反证：① 去掉允许面检查 ⇒ 越界拒绝红；② 去掉预算短路 ⇒ 重试/重拆计数红；
      ③ 去掉通知脱敏 ⇒ canary 落盘红；复原 `md5sum` 同。
- [x] 6.3 `openspec validate --all` 全绿后归档。

## 7. 文档与登记

- [x] 7.1 ADR-0270；台账 E216；`doc/04-testing/test-cases.md` §192。
- [x] 7.2 `doc/02-modules/orchestration.md`、`doc/03-interfaces/{orchestration,configuration,loop}-interface.md`。
- [x] 7.3 单次提交 `feat(orchestration): ...` + Co-Authored-By。
