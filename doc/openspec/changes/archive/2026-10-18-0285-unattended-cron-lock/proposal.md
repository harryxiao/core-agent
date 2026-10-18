# Proposal 0285 — 续跑批次单实例锁与 cron 运维闭环

## Why

对齐报告（`doc/01-architecture/claude-code-alignment.md`）把「常驻调度形态」列为 P1：续跑机制
（`task --resume-all` / `orchestration.auto_resume`）已齐备，但当前推荐形态是**外部 cron 周期
拉起**，而这条路径有两个缺口：

- **并发双跑**：cron 周期短于批次时长时，两个 `--resume-all` 会同时扫描同一批未完成任务并各跑
  一遍；`CheckpointStore` 跨进程是最后写者胜，`AutoResumeState` 的临时文件写也会互相覆盖。
  续跑路径上没有任何互斥。
- **没有运维文档**：cwd、状态目录、退出码、日志、护栏与「病态任务如何止血」均无说明，
  无人值守部署只能靠读代码猜。

本 change 增加跨进程单实例锁并补齐 cron 运维手册；不引入守护进程或 `scheduler` 子命令。

## What Changes

1. **锁助手**：`core.orchestration.state_files` 新增 fail-closed 的非阻塞
   `try_exclusive_file_lock`（POSIX `flock LOCK_EX|LOCK_NB` / Windows `msvcrt.LK_NBLCK`，
   锁文件 `0600`），返回 `acquired / busy / unavailable` 三态；既有 fail-open 的
   `exclusive_file_lock` 语义不变。
2. **批次互斥**：`_run_auto_resume` 在扫描检查点之前取
   `$CORE_STATE_DIR/.auto-resume.json.lock`，持有到整个批次结束；锁忙时立即跳过。
   显式 `--resume-all` 忙则退出 0（重叠是 cron 常态）；锁不可用时显式入口退出 1 提醒运维。
   自动续跑模式忙时跳过续跑，但本次新任务照常执行。
3. **规格**：`orchestration` ADDED「续跑批次单实例互斥」，明确锁范围只到续跑批次，
   不声称检查点文件获得跨进程单写者一致性。
4. **运维手册**：新增 `doc/05-development/unattended-ops.md`（cron/crontab 形态、退出码、
   护栏、日志、止血步骤与局限）。
5. **台账**：ADR-0275、known-risk E221、test-cases §197、模块/接口/对齐报告同步更新。

## Impact

- 受影响规格：`orchestration`（ADDED 续跑批次单实例互斥）。
- 代码：`src/core/orchestration/state_files.py`、`src/core/entry.py`；
  测试 `tests/test_auto_resume.py`（新增）与 `tests/test_unattended.py`（补测试隔离）。
- 兼容性：无冲突时行为逐字不变（仅多一个空锁文件）；不新增 flag/config；不新增依赖；
  不改后台登记/工作树 sidecar 使用的 fail-open 助手。
- 文档：新运维手册 + ADR/风险/用例索引 + 对齐报告 §3.8 与 P1 行。

## 不做（边界）

- 守护进程、`core-agent scheduler` 子命令、任务队列/队列视图/健康检查端点。
- systemd timer、Windows 计划任务示例（部署形态只覆盖 cron/crontab）。
- 阻塞等待/超时抢锁、PID 文件、锁过期回收、跨主机/分布式锁、NFS 一致性保证。
- `task --forget` 或检查点删除/配额 CLI（手册给出停机止血步骤并登记为缺口）。
- 把锁扩展到 fresh `task`、`task --resume <id>`、REPL、`serve` 的全局单写者改造。
- 真实 LLM 的 cron 长跑验收（并发语义用离线假运行时覆盖）。

## 风险

- 锁是平台原生**建议锁**：绕过本入口直接改状态目录、或在不支持 `flock` 的文件系统
  （部分 NFS/网络盘）上不保证互斥；文档明确单机本地盘形态。
- 批次挂死会占锁到进程退出，后续 cron tick 全部跳过并退出 0；需靠 `task_timeout` 与日志
  `[resume_skipped]` 频率发现。
- `--resume-all` 的 `force=True` 绕过退避与尝试上限：永久失败任务会每 tick 重试并通知。
- Windows 只做单元行为覆盖，未做手工端到端验证。
