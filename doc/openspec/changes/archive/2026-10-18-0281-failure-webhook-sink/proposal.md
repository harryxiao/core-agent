# Proposal 0281 — 失败通知 webhook sink

## Why

`0280` 的失败通知只落本地 JSONL：无人值守时没有人会在机器边上看文件。对比矩阵里「失败告警
可外接」是与 Claude Code 的明确差距；仓库既有的 IM 网关没有任何真实平台 Provider（只有
Protocol 与 fake），不能直接复用。需要一个**零三方依赖、缺省关闭**的远程推送原语。

## What Changes

- 新配置 `orchestration.failure_notify_webhook`（缺省空串 = 关闭）：HTTP(S) URL；校验期拒绝
  非 `http` / `https` scheme、缺 host、非字符串。三面（CLI / env / yaml）同源。
- 失败通知在既有 JSONL 文件 sink 之外，向该 URL `POST` 一份 JSON（`Content-Type:
  application/json`）：
  `{"text", "event", "task_id", "session_id", "code", "reason", "goal"}`。
  `text` 为一行摘要；`reason` / `goal` 均经 `redact_secrets` 且 500 字符截断。
- 单次尝试、`5s` 超时；失败只在 stderr 告警（**不打印 URL**——URL 可能自带令牌），不改变任务
  结局或退出码。文件 sink 与 webhook 互相独立：一个配置了就能用，两个都配置则都写。
- 覆盖范围与 `0280` 相同：终态失败、入口超时、自动续跑失败；`TASK_CANCELLED` 不通知。

## Impact

- `src/core/orchestration/notify.py`（新，stdlib `urllib.request`）。
- `src/core/configuration/manager.py`（1 个 ConfigSpec + 校验 + 访问器）。
- `src/core/entry.py`（`_notify_failure` 增 webhook 参数；入口与续跑传配置值）。
- 测试：新 `tests/test_failure_webhook.py`。
- 规格：`configuration` ADDED「失败通知 webhook 配置」；`orchestration` MODIFIED「任务失败
  通知 sink」。
- 文档：ADR-0271 / 台账 E217 / 测试节 §193 / 编排模块 §3.10 / configuration 与 orchestration
  接口文档。

## 不做（明确边界）

- 不做 IM 平台原生格式（飞书 / 企业微信 / Slack 的 `msg_type` 差异）：只保证通用 JSON +
  `text` 字段；平台适配层可用转发器承接。不引入三方 SDK。
- 不做重试队列 / 持久化待发送 / 签名校验；单次 best-effort。
- 不改 `failure_notify_file` 的既有字段与语义。
