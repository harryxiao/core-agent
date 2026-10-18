# Proposal 0278 — 未完成任务自动续跑（auto-resume）

## Why

长任务无人值守的最后一个编排缺口：进程崩溃/重启后，启动扫描**只呈现不重执行**
（`entry._surface_incomplete`），需要人或外部 watchdog 手动执行 `task --resume <id>`。
`0276`/`0277` 把记忆面收口后，编排队列里剩下的正是这条「恢复后谁来续跑」的运维缝。

## What Changes

- 新配置 `orchestration.auto_resume`（默认 `false`；CLI `--orchestration.auto-resume` /
  env `CORE_ORCHESTRATION_AUTO_RESUME`）——显式开启后，`core-agent task` 启动路径把
  未完成编排任务**自动续跑**（重建计划 / 已完成子集 / 交接结果 / 会话标识），
  默认关时维持「纯扫描 + 呈现」逐字不变。
- 新 CLI `core-agent task --resume-all`：显式续跑全部未完成任务（不受配置开关与退避限制）。
- 自动续跑**有界**：同一任务跨进程最多 3 次自动尝试；尝试间指数退避（60s 起、上限 3600s），
  计数与时间戳落盘 `$CORE_STATE_DIR/auto-resume.json`（0600）；达上限跳过并告警，
  人工 `--resume` 不受限。续跑失败不删除检查点。
- 跳过会话轮级检查点（`turn.`）与已完成（`done=true`）任务；损坏/无计划的检查点降级跳过。
- 新增 `TaskResume` 描述符与 `Runtime.pending_resumes()`（只读重建，不触发执行）。

## Impact

- `src/core/orchestration/auto_resume.py`（新）、`models.py` / `__init__.py`（`TaskResume`）、
  `src/core/runtime.py`（`pending_resumes` / `_task_resumes`）、
  `src/core/configuration/manager.py`（三面 + 校验 + 访问器）、`src/core/entry.py`（`--resume-all` 与自动续跑）。
- 测试：新 `tests/test_auto_resume.py`（配置 / 退避有界 / 重建描述符）；`tests/test_entry.py`
  补 `--resume-all` 与「新任务前自动续跑」。
- 规格：`orchestration` **ADDED**「未完成任务自动续跑」；`configuration` **MODIFIED**
  （新键）；`durability` **MODIFIED**（纯扫描语义增加显式 opt-in 例外）。
- 文档：ADR-0268 / 台账 E214 / `doc/04-testing/test-cases.md` §190 /
  `doc/02-modules/orchestration.md` / `doc/03-interfaces/configuration-interface.md`。

## 不做（明确边界）

- 不做守护进程 / cron / systemd 集成；不做跨进程运行锁（与既有 `--resume` 同局限）。
- 不自动续跑 `serve` / TUI / `mcp serve` 启动面（事件循环线程归属复杂，仍只呈现）。
- 不改检查点格式、不删除既有检查点、不改人工 `--resume` 行为。
- 零三方依赖；不改 `exclude_source_prefixes`；密钥不入状态文件/日志。
