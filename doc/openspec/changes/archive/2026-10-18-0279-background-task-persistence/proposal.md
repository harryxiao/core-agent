# Proposal 0279 — 后台子 Agent 跨重启登记与重入队

## Why

`tools.delegate(background=true)`（change 0270）把子 Agent 状态只放在**进程内**注册表：
进程重启后 `tools.tasks` 清单清空，用户/模型既看不到「哪些后台任务随重启被中断」，
也无法把它们重新入队。对比报告把这条列为 P0 长任务缺口 —— 无人值守场景下，重启即等于
静默丢失工作。`ProcessRegistry`（change 0259）已为 OS 后台进程建立「元数据落盘 + 重启可见」
先例，子 Agent 侧需要同等地基。

## What Changes

- `BackgroundAgentRegistry` 支持**有界落盘**：`$CORE_STATE_DIR/background-tasks.json`（0600、
  原子替换、version=1、最多 64 条、损坏容忍）。持久化字段：`task_id / agent_id / task /
  status / started_at / finished_at / session_id / error`；`task` 与 `error` 落盘前经
  `redact_secrets` 脱敏并有界。
- 重启加载时，落盘为 `running` 的任务 SHALL 映射为**新终态 `interrupted`**（不伪造
  `finished_at`、不自动重执行、不产生完成通知），并在 `tools.tasks` 中可见。
- 新工具 `tools.task_retry`：对 `interrupted / failed / cancelled` 的任务按存储的任务正文
  重新路由子 Agent 并 `spawn`；`running`（无需重试）与 `done`（已完成）结构化拒绝；
  新任务 id 返回。工具按词元判 `HIGH_RISK`（需审批），coeffect `task:write`；
  **只挂主工具面**，子 Agent 不可见。
- 注册表构造参数 `state_path=None` 时保持**纯内存**（既有直接构造与测试零变化）；
  runtime 组合根注入状态路径 ⇒ 生产路径始终登记。

## Impact

- `src/core/orchestration/background.py`（落盘 / 恢复 / `interrupted` / `task_retry_tool`）、
  `src/core/runtime.py`（状态路径 + coeffect `task:write` + 工具注册）。
- 测试：新 `tests/test_background_persistence.py`；`tests/test_phase13.py` 工具清单补一项。
- 规格：`orchestration` **ADDED**「后台任务跨重启登记与重入队」。
- 文档：ADR-0269 / 台账 E215 / `doc/04-testing/test-cases.md` §191 /
  `doc/02-modules/orchestration.md` §3.7 / `doc/03-interfaces/orchestration-interface.md`。

## 不做（明确边界）

- 不做后台子 Agent 的**自动**重执行（是否重入队由模型/人显式调用 `tools.task_retry` 决定）。
- 不恢复进程内 `asyncio.Task`、不跨进程共享运行中注册表；不做跨进程运行锁。
- 不落盘 `reply` 正文（重启后仅保留状态与错误；完成结果以原完成通知为准）。
- 不改 `BackgroundAgentRegistry` 的运行中上限 / 通知语义；零三方依赖。
