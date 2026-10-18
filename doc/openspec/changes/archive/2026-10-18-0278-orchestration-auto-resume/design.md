# Design 0278 — 未完成任务自动续跑

## D1 显式 opt-in，默认零行为变化

`orchestration.auto_resume` 缺省 `false`；关闭时 `task` 启动路径仍只扫描呈现（现行语义逐字不变）。
开启后由 `task` 入口作为 durability「续跑由调用方显式触发」中的**调用方**自动触发——
配置开关即显式授权，不违反「启动扫描默认纯扫描」的既有裁决。

## D2 有界自动尝试（跨进程）

- 常量（不做配置旋钮）：`MAX_ATTEMPTS = 3`、`BASE_DELAY_S = 60`、`MAX_DELAY_S = 3600`。
- 状态文件 `$CORE_STATE_DIR/auto-resume.json`：`task_id → {attempts, last_ts}`，0600 原子写。
- 到期判据：`attempts < 3` 且 `now - last_ts >= min(60·2^(attempts-1), 3600)`
  （首次尝试后等 60s，随后每次翻倍，封顶 3600s）。
- 尝试前先记一次（崩溃也会消耗尝试数，保守）；成功清零；失败保留检查点，下次启动退避后重试。
- 达上限：跳过并告警；人工 `task --resume <id>`（原有入口）**不读**该状态，始终可用。
- 状态文件损坏 ⇒ 告警后按空状态处理；已消失任务的状态在扫描时清退。

## D3 重建口径与人工 `--resume` 同源

`Runtime.pending_resumes()` 只读检查点并重建 `TaskResume`（plan/completed/results/session），
与 `entry._task --resume` 的字段来源一致；跳过 `done=true`、`turn.` 前缀与无可解析计划者。
每条任务取**时间戳最新**的可读检查点（不是落盘末元素）。

## D4 执行位置

仅 `core-agent task` 入口：入口已是同步 CLI，续跑逐条 `asyncio.run(astream)` 串行执行，
与既有 `task --resume` 完全同一条流式管线（进度事件照常打印）。
`--resume-all` 为显式入口，**忽略**退避/上限（运营商显式重试），仍记录尝试并在成功时清零。
`serve` / TUI / `mcp serve` 不自动执行（避免跨事件循环共享调度器），文档明示。

## D5 安全

状态文件只存 task_id / 计数 / 时间戳，不含任务正文、记忆或密钥；告警只报 task id。
检查点损坏降级跳过（只报 task id），不中断其余任务续跑。

## 反证

1. 移除 `pending_resumes` 的 `done` 过滤 ⇒ 已完成任务被续跑（用例红）。
2. 移除退避/上限判据 ⇒ 有界性用例红。
3. 默认关闭时仍续跑 ⇒ 「默认只呈现」用例红。

## 已知局限

- 无跨进程运行锁：两个进程同时 `task` 可能同时续跑同一任务（与既有 `task --resume` 同）。
- 每次重启重置进程内状态机，但自动尝试计数跨进程持久化；上限后需人工介入或删状态文件。
- 任务级失败若源于永久性配置错误，会在 3 次尝试内反复失败后才静默（告警仍可见）。
