# 无人值守运维：cron + `task --resume-all`

> 适用版本：change `0285` / ADR-0275。本文只覆盖 **cron / crontab** 形态；不提供守护进程、
> `scheduler` 子命令、systemd timer 或 Windows 计划任务。
>
> 定位：Core-Agent 不内置调度器。由外部 cron 周期执行 `core-agent task --resume-all`，
> 把「未完成的编排任务」重新拉起。幂等性由**续跑批次单实例锁**保证（同一次只跑一个批次）。

## 1. 前提

| 项 | 要求 |
|---|---|
| 工作目录 | 必须 `cd` 到**项目根**：工具相对路径、项目 `Core.md`、cwd 的 `config.yaml` 都以 cwd 为基准 |
| 状态目录 | `CORE_STATE_DIR` 建议**每项目独立**；缺省是全局 `~/.core/state` |
| 配置 | `config.yaml` 放在项目根或 `~/.core-agent/config.yaml`；密钥经配置 / `CoeffectResolver` 注入 |
| 权限 | `task` 无交互审批通道，高风险动作 fail-closed；需要自动写入时显式配置 `permission.mode: auto-approve`，并用 `permission.auto_approve_coeffects` / `permission.auto_approve_commands` 收窄允许面 |
| 护栏 | 建议设置 `orchestration.task_timeout`（缺省 `0` = 不设限）、`orchestration.task_token_budget`、`orchestration.failure_notify_file` / `failure_notify_webhook` |

密钥只引用不读取：**不要把密钥、令牌或任务正文写进 crontab、命令行参数或日志**。

## 2. crontab 示例

```cron
# 每 10 分钟续跑一次；输出追加到私有日志（日志目录自行创建并设 0700）
*/10 * * * * umask 077; cd /path/to/project && CORE_STATE_DIR=/path/to/state/project /path/to/venv/bin/core-agent task --resume-all >> /path/to/logs/core-agent-resume.log 2>&1
```

说明：

- `CORE_STATE_DIR` 必须是**绝对路径**；不要依赖 cron 的 HOME。
- 使用虚拟环境里的 `core-agent`（或其绝对路径），不要依赖 cron 的 `PATH`。
- 先用同一命令手工跑一次，确认能装配、能找到配置、无待续任务时输出
  `无未完成任务（续跑扫描为空）`。
- 日志轮转交给外部工具（logrotate 等）；本文不生成滚动文件。

## 3. 退出码与日志

| 退出码 | 含义 |
|---|---|
| `0` | 无待续任务；或本批次全部成功；或**另一实例正在跑**（`[resume_skipped]`） |
| `1` | 用法错误 / 配置装配失败 / 至少一个任务失败或超时 / **续跑锁不可用** |

- `[resume_skipped] 另一个续跑实例正在运行`：cron 重叠属常态，不告警。
- `[resume_skipped] 续跑锁不可用（无法创建锁文件）`：状态目录权限/磁盘问题；cron 会以
  退出码 1 提醒，需人工处理。
- 若频繁出现 `[resume_skipped]` 且没有其他实例在跑，检查批次是否挂死（见 §5）。

## 4. 锁语义

- 锁文件：`$CORE_STATE_DIR/.auto-resume.json.lock`，`0600`，**不删除**（残留空文件不阻塞）。
- 获取时机：扫描检查点**之前**；持有到整个批次结束（扫描、逐任务执行、续跑状态写回）。
- 非阻塞：抢不到立即跳过，不排队、不等待。
- 崩溃释放：进程退出（含崩溃）由操作系统释放；无需手工清锁。
- 作用域：只串行化**续跑批次**。它**不**串行化 fresh `task <目标>`、`task --resume <id>`、
  REPL 或 `serve`；`checkpoints.jsonl` 仍是「最后写者胜」，没有跨进程单写者保证。
  同一 `CORE_STATE_DIR` 下**不要**并发跑无关任务。
- 建议锁：只在单机本地盘上保证；NFS / 网络盘 / 某些 WSL 挂载不保证互斥。

## 5. 停止一个「病态」任务

`--resume-all` 使用强制模式，绕过自动续跑的退避与尝试上限：一个永久失败的任务会被**每个
tick 重试**并重复通知。用 `task --forget <task-id>` 止血（change `0286` / ADR-0276）：

1. 注释掉 crontab 中的续跑行（或 `crontab -e` 暂时移除），确认没有正在运行的
   `core-agent task` 进程。
2. 备份：`cp "$CORE_STATE_DIR/checkpoints.jsonl" "$CORE_STATE_DIR/checkpoints.jsonl.bak"`。
3. 显式遗忘该任务：

   ```bash
   cd /path/to/project
   CORE_STATE_DIR=/path/to/state/project core-agent task --forget task-xxxxxxxx
   ```

   输出 `[checkpoints_forgotten] task=... deleted=N`。该命令删除该任务的**全部**检查点
   （含 pinned）并清除 `auto-resume.json` 中的退避记录；任务 id 不存在时以退出码 1 结束。
4. 恢复 crontab，手工跑一次 `task --resume-all` 确认不再出现该任务。

> 删除不可逆；先用 `time-travel` / 备份确认不需要回滚。维护入口与续跑批次共用
> `.auto-resume.json.lock`，批次运行中会以 `[checkpoints_locked]` 拒绝执行。

### 一次性清理检查点

保留策略（`durability.retention.max_count` / `time_window_s`）之外，可手工执行一次：

```bash
core-agent task --prune-checkpoints --max-count 500          # 未 pinned 最多保留 500
core-agent task --prune-checkpoints --older-than-s 604800    # 删除 7 天前的未 pinned
```

两个边界可同时给出；至少给一个。pinned 检查点永不删除；输出
`[checkpoints_pruned] deleted=N kept=M pinned=P`。清理一次原子落盘，不会留下半截文件。

## 6. 已知局限

- 批次挂死会占锁到进程退出，期间所有 tick 跳过并退出 0；用 `task_timeout` + 日志监控兜底。
- `task_token_budget` 按**单次尝试**累计，不是跨续跑的全局预算。
- 续跑依赖已有检查点：尚未完成首个波次的任务没有检查点，不会被 `--resume-all` 拉起。
- 锁是建议锁，不能防止绕过入口直接改写状态文件。
- `--forget` / `--prune-checkpoints` 只与续跑批次互斥；并发 fresh `task` 写入时仍是
  最后写者胜（同一状态目录的单写者约定不变）。
- `--prune-checkpoints --max-count N` 只约束未 pinned 集，最终保留总数可能为 `N + pinned`。
- Windows 未做手工端到端验证（单元行为已覆盖）。
- 不提供队列视图、健康检查端点、平滑升级；这些属于后续「常驻调度」评估。
