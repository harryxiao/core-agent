# Design 0281 — 失败通知 webhook sink

## D1 通用 JSON POST，不做平台方言

请求体固定为

```json
{"text": "[core-agent] 任务失败 task-x (CODE): reason",
 "event": "task_failed", "task_id": "...", "session_id": "...",
 "code": "...", "reason": "...", "goal": "..."}
```

`text` 让 Slack 兼容端点（`{"text": ...}`）开箱可用；结构化字段让自建转发器无需解析文本。
飞书 / 企业微信的 `msg_type` / `msgtype` 方言不在本 change 内——用转发器或后续适配层承接。
不新增依赖：`urllib.request` 已是仓库既有 HTTP 原语（`builtin.web_fetch` / `judgment` 同源）。

## D2 配置与校验

- 键：`orchestration.failure_notify_webhook`；CLI `--orchestration.failure-notify-webhook`；
  env `CORE_ORCHESTRATION_FAILURE_NOTIFY_WEBHOOK`；默认 `""`。
- 校验：必须为字符串；非空时 `urllib.parse.urlsplit` 结果 scheme ∈ {`http`, `https`} 且
  `netloc` 非空，否则启动阻断（错误信息只回显**键名与合法形态**，不回显 URL 值）。
- 访问器 `ConfigManager.orchestration_failure_notify_webhook() -> str`。

## D3 发送点与失败语义

- `notify.post_failure_webhook(url, payload, *, timeout=5.0)`：构造 `Request`（POST、JSON、
  `User-Agent`），`urlopen` 并读尽关闭；任何异常原样上抛，由调用方兜底。
- `entry._notify_failure(..., webhook="")`：先写文件 sink（若配置），再推 webhook（若配置）。
  两个 sink **互不影响**：文件写失败不影响 webhook，webhook 失败不影响文件与任务结局。
- 告警文本只含异常类名与目标键名，**绝不拼接 URL 或 `str(exc)`**（`HTTPError.__str__` 会带
  URL，URL 可能内嵌令牌）。

## D4 同步、单次、有界

`_notify_failure` 是同步函数，webhook 在任务终态路径上同步调用：最坏阻塞 `timeout=5s`，
只发生在任务已经失败的收口时刻；不做后台队列（会把「进程即将退出」与「网络在途」耦合，
且无人值守场景下丢通知比多等 5 秒更糟）。单次不重试：重试会放大故障时的等待与重复告警。

## 反证

1. 摘掉 `text/reason/goal` 的 `redact_secrets` ⇒ canary 落盘/入请求体用例红。
2. 摘掉 scheme/host 校验 ⇒ `file://` 配置阻断启动用例红。
3. 摘掉 URL 不回显约束（告警拼接 URL）⇒ URL 含令牌时 stderr 泄漏用例红。

## 已知局限

- 只保证通用 JSON，不保证各 IM 平台原生渲染。
- 同步单次、无队列：接收端不可用即丢该条通知。
- URL 明文存于配置文件（与 API key 同层），依赖文件权限；不引入加密。
