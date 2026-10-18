# Design 0286 — 检查点运维入口

## D1 两个动词挂在 `task` 下，而非新命令组

`task` 已是编排任务的生命周期入口（起任务、续跑、续跑批次），检查点正是它的状态载体。
新增 `checkpoint` 顶层命令组会引入新的发现面与文档面，却只服务两个动词。因此：

- `task --forget <task-id>`
- `task --prune-checkpoints --max-count N [--older-than-s S]`

互斥由 `_task` 入口显式校验（`<目标>` / `--resume` / `--resume-all` / `--task-id` 均不可组合），
错误走 stderr + 退出 1，不静默忽略。

## D2 `--forget` 语义：精确任务、含 pinned、清退避

- **精确匹配 `task_id`**：不按前缀、不按会话、不碰其他任务。
- **含 pinned**：pinned 的语义是「不被自动清理」，不是「不可显式删除」。若显式遗忘跳过 pinned，
  病态任务会留下一个永久续跑源（最新快照仍可被 `_task_resumes` 选中）。
- **清除 `AutoResumeState`**：删除检查点后调用 `clear(task_id)`；否则残留账本虽会被下一次
  `retain()` 顺手清掉，但会让「forget 后仍显示有退避记录」的观感与状态文件不一致。
- **0 条即非零退出**：这是人工/脚本的显式点杀，拼错 id 静默成功比失败更危险。

顺序：取锁 → 打开 store → 收集该任务 id → `delete_many` → `AutoResumeState.clear` → 输出计数。
先删检查点再清账本：即使清账本失败（OSError 被 `AutoResumeState` 内部吞掉并告警），
检查点已消失，病态任务不会再被扫描。

## D3 `--prune-checkpoints` 复用保留语义

`RetentionManager` 已有 max_count / time_window / storage_quota 三通道。本入口只暴露前两个
（与生产接线一致），规则：

- max_count：从未 pinned 集按 ts 升序删除，直到未 pinned 数量 ≤ N；
- time_window：删除未 pinned 且 `ts < now - S`；
- 两者同时给出：并集；
- pinned：任何情况下都不删。

实现上给 `RetentionManager` 增加 `prune(policy) -> int`：收集待删 id 后一次
`CheckpointStore.delete_many`，避免老实现每条一次全文件重写（turn 检查点可达数千条）。
`apply(policy)` 改为先调 `prune`，再执行既有 quota 分支——quota 分支保持逐条删除与原抛出
`RETENTION_QUOTA_EXCEEDED` 的时机不变（该通道未接生产，改动它是无谓风险）。

## D4 锁：与续跑批次共用同一把锁

维护入口读写同一个 `checkpoints.jsonl`，而 `0285` 已经定义了续跑批次锁。复用而非另造：

- 锁路径 `$CORE_STATE_DIR/.auto-resume.json.lock`；
- `busy` / `unavailable` 一律 fail-closed：`[checkpoints_locked]` + 退出 1；
- 锁覆盖「打开 store → 删除 → 落盘 → 清退避」全过程。

不扩展到 fresh `task` / REPL / `serve`：它们不取这把锁，`CheckpointStore` 仍是最后写者胜。
运维手册继续声明「同一状态目录不要并发跑无关任务」。

## D5 输出与脱敏

- `[checkpoints_forgotten] task=<id> deleted=<n>`
- `[checkpoints_pruned] deleted=<n> kept=<m> pinned=<p>`
- 未找到：stderr `未找到任务 <id> 的检查点`
- 锁冲突：stderr `[checkpoints_locked] 续跑批次正在运行或锁不可用，未修改任何检查点`

任务 id 是运维标识（`--resume` 报错已回显同级别信息）；任务目标、子任务回复、snapshot 内容
一律不打印。`AutoResumeState` 的告警只含文件名。

## D6 不做模型工具

运维删除面只给 CLI。暴露为工具会要求审批通道、写入工具 schema 与权限词元，收益为零：
模型没有「删除某任务检查点」的正常推理需求；而这正是最容易被提示注入诱导的破坏性动作。
显式 CLI 调用即授权。

## 被拒方案

| 方案 | 拒绝理由 |
|---|---|
| 直接编辑 `checkpoints.jsonl`（现状止血步骤） | 绕过原子写/损坏容忍，半截文件会让整个 store 降级 |
| 新增 `checkpoint` 顶层命令组 | 两个动词撑不起新命名空间；与 `task` 生命周期割裂 |
| `--forget` 静默成功（0 条也退出 0） | 拼错 id 变成无声失败，病态任务继续被 cron 重试 |
| `--forget` 跳过 pinned | 留下最新快照 ⇒ `_task_resumes` 仍选中，止血失败 |
| 维护入口阻塞等待续跑锁 | cron 批次可能很长，维护会被挂住；非阻塞 + 明确退出码更适合运维 |
| 把 `--resume-all` 改成受退避约束 | 显式入口的「强制重试」是既有契约；本 change 提供止血面而非改语义 |

## 已知局限

- 不可逆删除，无回收站；只能靠备份或 `time-travel` 之外的既有副本。
- `--max-count` 只约束未 pinned 集，最终保留总数可能为 `N + pinned`。
- 锁只与续跑批次互斥；fresh `task` 并发时仍可能最后写者胜。
- NFS/网络盘上的建议锁不保证互斥（沿 0285）。
- 清除 `auto-resume.json` 失败只告警（`AutoResumeState` 自吞 OSError），不影响退出码。
