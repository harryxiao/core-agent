# Design 0280 — 无人值守 profile

## D1 profile = 既有 auto-approve + 三个可选护栏

不新增权限模式：`permission.mode=auto-approve` 是「谁来裁决」的开关；本 change 增加的是
**放行面**与**任务级护栏**。四项配置缺省值（`"" / 0 / 0 / ""`）全部等价于引入前行为，
因此不设额外总开关 —— 每个旋钮本身就是 kill-switch。

## D2 允许面：按声明 coeffect 收窄 auto-approve

- 取值：逗号分隔的 coeffect 名（形如 `namespace:action`），校验期逐项匹配
  `^[a-z][a-z0-9_-]*:[a-z][a-z0-9_-]*$`，去重保序；空/未配置 ⇒ 不限制。
- 判定：**只在** `PermissionModeGate` 的 `AUTO_APPROVE` 分支生效，且采用**全含**语义 ——
  动作声明的 coeffect 集合必须是白名单子集；任一不在 ⇒ `PERMISSION_DENIED`
  （`AccessControlError`，经 `PermissionGuard.confirm` 转 `deny`）。
- 空 coeffect 的工具（如 `tools.context_read`）不受影响：白名单约束的是**声明的副作用面**，
  coeffect 声明纪律仍是唯一真源（未声明的副作用属 cocoeffect 解析层的职责）。
- 其余三档忽略该配置（read-only / high-risk-block 的拒绝和 interactive 的审批语义不变）。
  guardrail 在 `authorize` 通过后独立检查，不受影响。

## D3 整任务时限：入口层 `asyncio.wait_for`

不在调度器内部加墙钟：调度器还被 `serve` / TUI / 程序化 `astream` 消费，入口层是
「无人值守任务」的唯一语义点。`task` 入口（新任务、`--resume`、自动续跑与 `--resume-all`
逐任务）以 `asyncio.wait_for(stream, timeout)` 包住**完整**任务流（拆解 + 波次 + 判定）。
超时 ⇒ 取消流；`astream` 的 `finally` 照常 `_release`（状态 FAILED、trace `task_aborted`），
**最后一次波次检查点保留**。入口打印 `[task_timeout]`、退出码 1、写通知（`TASK_TIMEOUT`）。
`0` ⇒ 不包 `wait_for`，行为与引入前逐字一致。

## D4 整任务 token 预算：调度器累计 + fail-closed 短路

- `TaskScheduler(task_token_budget=0)`：构造缺省 `0` = 关闭；组合根从配置注入。
- `LoopResult` 新增 `token_used: int = 0`；`DefaultLoop` 以 `ctx.token_used` 填充。
  这是**子循环收尾轮**的上下文记账（不是累计账单、也不是多轮求和），故任务级累计是
  粗粒度上界估计 —— 在 ADR 与接口文档如实标注。
- `_run_subtask` 在 `collect_result` 返回后累计；累计值 `>= budget` ⇒ 该子任务以
  `TASK_TOKEN_BUDGET_EXCEEDED` 失败返回（即使验收本可通过），事件照常 `subtask_completed`
  （`ok=false`）。
- `_execute_wave` 见到该码 ⇒ **不进重试**；`_stream_task` 见到该码 ⇒ **不重拆**，直接
  FAILED（`extra` 带 `token_used` / `token_budget`）。
- 任务级累计在 `_release` 清除（终态/断流/取消任一退出路径）；并发波次各自完成后累加，
  可能小幅越过预算（按「完成时判定」，不做跨协程预留）。

## D5 失败通知：本地 JSONL sink

- `_notify_failure` 追加一行 `{"ts", "event":"task_failed", "task_id", "session_id", "code",
  "reason", "goal"}`；`reason` / `goal` 经 `redact_secrets` 且截断 500 字符。
- 新建文件 `0600`，父目录按需创建；**不**改既有文件权限；写入失败只 stderr 告警。
- 触发点：`_stream_task` 收到 `task_failed`（排除 `TASK_CANCELLED` —— 主动取消不是故障）；
  超时分支显式写入（此时无 `task_failed` 事件）。
- 不做重试/轮转/远程推送；文件增长由运维侧负责。

## 反证

1. 移除 auto-approve 分支的白名单判定 ⇒ 越界 coeffect 拒绝用例红。
2. 移除 token 预算在重试/重拆前的短路 ⇒ 「不重试不重拆」计数用例红。
3. 移除通知正文的 `redact_secrets` ⇒ 密钥 canary 出现在通知文件（用例红）。

## 已知局限

- token 预算低估真实消耗（每子任务只记收尾轮上下文；任务级判定器与拆解调用不计）。
- 超时终止依赖协作取消：模型调用若在底层阻塞（无异步取消点），取消可能延迟生效。
- 通知文件非原子追加不保证跨进程行完整（单用户 CLI 视为可接受）；不轮转。
- 白名单按**声明** coeffect 匹配：coeffect 声明缺失/错误的工具仍可能绕过（既有声明纪律问题）。
