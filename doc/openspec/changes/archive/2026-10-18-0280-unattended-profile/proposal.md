# Proposal 0280 — 无人值守 profile（允许面 / 整任务护栏 / 失败通知）

## Why

`permission.mode=auto-approve` 目前是**全有或全无**：无人值守场景要么全放行（模型可执行任意
已声明 coeffect 的副作用），要么退回 interactive 而在无审批通道时 fail-closed 停摆。同时
`task` 入口只有**子任务级**交接超时（`orchestration.subtask_timeout`），没有整任务墙钟上限；
编排层没有跨子任务的 token 预算；任务失败只打印到 stderr，无人值守时无人知晓。

对比报告的 P1 项「无人值守 profile」要求把这三块补成可组合的护栏，且**缺省全部关闭**
（既有行为逐字不变）。

## What Changes

- `permission.auto_approve_coeffects`：auto-approve 档下按**声明 coeffect 白名单**收窄放行面
  （逗号分隔；空 = 全放行 = 现状）。动作声明的**任一** coeffect 不在白名单内 ⇒
  `PERMISSION_DENIED`（fail-closed）。仅作用于 auto-approve；其余三档语义不变。
- `orchestration.task_timeout`：整任务墙钟时限（秒；`0` = 不设限 = 现状）。在 `task` 入口用
  `asyncio.wait_for` 包住完整任务流（含自动续跑与 `--resume`）；超时终止任务、保留检查点、
  退出码 1、写失败通知（`TASK_TIMEOUT`）。
- `orchestration.task_token_budget`：整任务 token 预算（`0` = 关闭 = 现状）。调度器累计各子任务
  的 `LoopResult.token_used`（子循环收尾时的上下文记账估算）；达到上限 ⇒
  `task_failed`（`TASK_TOKEN_BUDGET_EXCEEDED`），**不重试、不重拆**，直接 FAILED。
  `LoopResult` 新增 `token_used` 字段（缺省 `0`）。
- `orchestration.failure_notify_file`：失败通知 sink（空 = 关闭 = 现状）。任务终态失败（含超时、
  自动续跑失败；**不含用户主动取消**）时向该文件追加一行 JSON（JSONL），正文经
  `redact_secrets` 且逐字段有界；新建文件 `0600`；写失败只在 stderr 告警，不改变任务结局。

## Impact

- `src/core/configuration/manager.py`（4 个 ConfigSpec + 校验 + 访问器）。
- `src/core/permission/{policy,guard}.py`（允许面注入与判定）。
- `src/core/loop/{protocol,default}.py`（`LoopResult.token_used`）。
- `src/core/orchestration/{errors,scheduler}.py`（新错误码 + 预算累计与短路）。
- `src/core/entry.py`（整任务时限 + 通知 sink）、`src/core/runtime.py`（组合根接线）。
- 测试：新 `tests/test_unattended.py`。
- 规格：`configuration` / `permission` / `orchestration` ADDED；`loop` ADDED。
- 文档：ADR-0270 / 台账 E216 / `doc/04-testing/test-cases.md` §192 /
  `doc/02-modules/orchestration.md` / `doc/03-interfaces/{orchestration,configuration,loop}-interface.md`。

## 不做（明确边界）

- 不新增第五种权限模式；「无人值守 profile」= `auto-approve` + 上述可选护栏的组合。
- notify sink 只落本地文件：不做 webhook / IM 推送 / 重试队列（网络侧副作用不在本 change）。
- token 预算不是账单口径：`LoopResult.token_used` 是**上下文记账估算**（子循环收尾轮），
  不累加同一子循环内的多轮调用，也不覆盖任务级判定器消耗 —— 作为粗粒度熔断，不承诺精确。
- 不改 guardrail（安全机制仍与权限档正交）、不改 `exclude_source_prefixes`、零三方依赖。
