# Proposal 0286 — 检查点运维入口：显式遗忘与一次性清理

## Why

`0285` 收口了 cron 形态的续跑互斥与运维手册，但手册里对「永久失败任务」只能给出
**停机 → 备份 → 手工删除 `checkpoints.jsonl` 中 `snapshot.task_id` 行** 的止血步骤。
这不是可接受的日常运维面：

- `task --resume-all` 的 `force=True` 绕过退避与尝试上限 ⇒ 病态任务每个 cron tick 都会被
  重跑并重复发送失败通知，直到有人手工改文件。
- 保留策略虽已接线（`durability.retention.max_count` / `time_window_s`），但只能靠改配置、
  等下一次检查点写入才生效；磁盘吃紧或临时清理时没有一次性入口。
- 直接编辑 `checkpoints.jsonl` 绕过 `CheckpointStore` 的原子写与损坏容忍，容易写出半截文件。

本 change 增加两个**显式 CLI 运维动词**，不新增后台行为、不新增配置面、不暴露给模型工具面。

## What Changes

1. **`task --forget <task-id>`**：删除该 `task_id` 的**全部**检查点（含 pinned——显式操作优先于
   自动清理保护），并清除 `auto-resume.json` 中该任务的退避/尝试记录；只删精确匹配的任务。
   删除 0 条时退出码 1（提示任务不存在），便于脚本发现拼写错误。
2. **`task --prune-checkpoints --max-count N` / `--older-than-s S`**：一次性按既有保留语义
   清理**未 pinned** 检查点；两个边界至少给一个，可同时给。输出只含删除/保留/pinned 计数。
3. **与续跑批次互斥**：两个动词执行前都取 `0285` 的 `.auto-resume.json.lock`；锁忙或不可用
   一律 fail-closed（不删除、退出 1、stderr `[checkpoints_locked]`），避免与正在写检查点的
   续跑批次互相覆盖。
4. **批量删除**：`CheckpointStore.delete_many` 单次原子落盘；`RetentionManager.prune` 复用它，
   使一次性清理不是 O(n²) 次全文件重写（`apply` 语义与既有调用方不变）。
5. **规格**：`orchestration` ADDED「检查点运维入口」；`durability` 接口文档补充批量删除。
6. **运维文档**：`unattended-ops.md` 的止血步骤改为 `task --forget`，补充 `--prune-checkpoints`。

## Impact

- 受影响规格：`orchestration`（ADDED）。
- 代码：`src/core/entry.py`（argparse + 两个维护入口）、
  `src/core/durability/store.py`（`delete_many`）、`src/core/durability/retention.py`（`prune`）。
- 测试：新增 `tests/test_checkpoint_maintenance.py`；`tests/test_durability.py` 补批量删除。
- 兼容性：既有命令、配置与默认行为逐字不变；不新增依赖；不改 `CheckpointStore` 单写者假设。
- 文档：ADR-0276、known-risk E222、test-cases §198、模块/接口/用户/对齐报告同步。

## 不做（边界）

- 不新增 `checkpoint` 顶层命令组、不提供列表/导出/恢复 UI（`time-travel` 与 `--resume` 已有）。
- 不暴露为模型工具（无 `tools.checkpoint_*`），因此不新增审批路径：显式 CLI 调用即授权。
- 不删除后台子 Agent 登记、trace、memory 等其他状态文件。
- 不做并发全局单写者改造：维护入口只与续跑批次互斥，fresh `task` / REPL / `serve` 仍按既有
  单写者约定运行。
- 不改自动续跑的重试语义（`--resume-all` 仍为 force）；本 change 提供的是**止血面**。
- 不接存储配额通道（既有 ADR-0198 决策不变）。

## 风险

- `--forget` 是不可逆删除：靠精确 `task_id` + 锁 + 计数输出降低误操作；任务正文与密钥永不回显。
- `--prune-checkpoints` 的 `--max-count` 只统计未 pinned 集：pinned 不计入上限，可能保留数
  超过给定 N（与 `RetentionManager` 既有语义一致）。
- 维护入口只与续跑批次互斥；若同时有 fresh `task` 写检查点，仍是最后写者胜（既有约定）。
- 锁在部分 NFS/网络盘上不保证互斥（沿 0285 局限）。
