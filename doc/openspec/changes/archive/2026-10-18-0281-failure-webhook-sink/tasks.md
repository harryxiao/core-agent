# Tasks 0281 — 失败通知 webhook sink

> 验证目标：`failure_notify_webhook` 三面齐备、非法 URL 阻断启动；失败时 POST 脱敏 JSON、
> 5s 超时；空配置零网络 I/O；推送失败只告警、不改变任务结局且不回显 URL。

## 1. 规格与测试先行

- [x] 1.1 spec delta：`configuration` ADDED；`orchestration` MODIFIED。
- [x] 1.2 新 `tests/test_failure_webhook.py`（配置 / 发送 / 脱敏 / 失败兜底 / 取消不通知）。

## 2. 配置层

- [x] 2.1 `orchestration.failure_notify_webhook` ConfigSpec + 常量（三面）。
- [x] 2.2 校验：字符串、`http(s)` scheme、非空 host；错误信息不回显 URL。
- [x] 2.3 访问器 `orchestration_failure_notify_webhook() -> str`。

## 3. 发送与接线

- [x] 3.1 新 `src/core/orchestration/notify.py::post_failure_webhook`（stdlib、5s）。
- [x] 3.2 `entry._notify_failure` 增 `webhook=`；文件与 webhook 互不影响；告警不含 URL。
- [x] 3.3 `_stream_task` / `_run_task_stream` / `_task` / `_run_auto_resume` 透传配置值。

## 4. 验证

- [x] 4.1 四门禁（ruff check / ruff format --check / pyright / pytest）。
- [x] 4.2 反证 3/3（摘脱敏 / 摘 scheme 校验 / 告警带 URL ⇒ 各红；复原 `md5sum` 同）。
- [x] 4.3 `openspec validate --all` 全绿后归档。

## 5. 文档与登记

- [x] 5.1 ADR-0271；台账 E217；`doc/04-testing/test-cases.md` §193。
- [x] 5.2 `doc/02-modules/orchestration.md`、`doc/03-interfaces/{orchestration,configuration}-interface.md`。
- [ ] 5.3 单次提交 `feat(orchestration): ...` + Co-Authored-By。
