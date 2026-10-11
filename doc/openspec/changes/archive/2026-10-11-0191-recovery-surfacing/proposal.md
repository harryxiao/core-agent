# Change 0191 — 恢复呈现接线（启动扫描+呈现，续跑仍显式）

## Why

长任务评估取证（2026-10-11）——**崩溃恢复能力存在却无人触发**：

1. **`Runtime.recover()` 零生产调用方**（`src/core/runtime.py:183-185`）：扫描检查点、对无 `done`
   标记的任务 `restore` + `resume`（幂等续跑）的能力齐备，但**没有任何入口调用它** ⇒ 未完成任务
   跨进程重启后**无人知晓**，续跑全靠人工记 task-id。
2. **一坏任务炸全扫**：`_recover_incomplete`（`runtime.py:1133-1139`）对每个未完成任务调
   `recovery.restore(cp.task_id)`，而 `restore` 在「该任务检查点全部无有效快照」时**整体
   `raise DurabilityError(CHECKPOINT_NOT_FOUND)`**（`manager.py:119-123`）——调用点**无
   try/except** ⇒ 单个不可恢复任务会**中断整轮扫描**，其余任务的续跑句柄全部丢失。这与首轮
   `get_snapshot` 对 corrupt 的既有口径（`runtime.py:1125-1128` 捕获 `DurabilityError` 后
   `continue`）**方向相反**，是结构性缺口。
3. **两种「最新检查点」定义并存**：CLI `--resume` 取 `cps[-1]`（**文件落盘序**，`entry.py:1720`），
   而崩溃恢复 `restore` 取 **ts 序**（`manager.py:102-106` `reverse=True`）⇒ 续跑可能取到**非最新**
   检查点，重建出陈旧计划。

## What Changes

- **启动扫描 + 呈现（不重执行）**：`serve` 启动与 CLI `task` 启动调 `runtime.recover()` ⇒ 有未完成
  任务 ⇒ 告警 + 打印「N 个未完成任务：`task --resume <id>` 可续跑」；**SHALL NOT 自动重新执行**
  （用户裁决①：符合 P2 —— 副作用不自动重放；`resume()` 现状无 replay 回调 = 纯扫描，诚实保留）。
- **降级不炸全扫**：`_recover_incomplete` 对 `recovery.restore` 包 `try/except DurabilityError`
  ⇒ 跳过该任务 + 告警，其余任务照常返回续跑句柄（与 corrupt 检查点既有口径对齐）。
- **恢复句柄标识所属任务**：`RestoreHandle` 增 `task_id` 字段 ⇒ 呈现「哪些任务未完成」无需
  旁路扫描（恢复句柄即自然载体）。
- **「最新检查点」对齐 ts 序**：CLI `--resume` 取**时间戳最新**检查点（与 `restore` 同口径）。
- 规格变更：`durability`「崩溃恢复」（纯扫描语义 + 降级跳过 + 句柄标识任务）；`cli-ops`
  「会话命令族与交互入口续聊」（入口启动呈现 + `--resume` ts 序）。

## Impact

- **改动面**：`src/core/durability/models.py`（`RestoreHandle` 加字段）、
  `src/core/durability/manager.py`（`restore` 构造补 `task_id`）、`src/core/runtime.py`
  （`_recover_incomplete` 包 try/except + 告警）、`src/core/entry.py`（`_surface_incomplete`
  助手 + `_build_ui` 增 `surface_recovery` 形参 + `_serve` 传入 + `_task` 启动扫 + `--resume`
  ts 序）；测试面 `tests/test_durability_crash.py` / `tests/test_phase15.py` / `tests/test_entry.py`
  （替身补 `recover` 与 `ts`）。
- **零改动面**：`scheduler`（本 change 不碰编排）；`resume()` 语义（无 replay = 纯扫描的现状
  诚实保留，不加 replay 面）；CLI `run`/REPL/`app` 入口（不呈现，避免既有输出面漂移）。
- **兼容性**：`RestoreHandle` 加**非缺省**字段是**破坏性接口变更**，但全仓构造点仅 `manager.py:113`
  一处 + 测试构造点（若替身恰好造 `RestoreHandle` 则同步）；`--resume` 由文件序改 ts 序只在
  「落盘序 ≠ 时间序」时改变取值（正常追加落盘两者一致 ⇒ 行为逐字不变）。

## Non-goals

- **不**自动续跑 / replay 重执行（用户裁决①：续跑仍**显式**；副作用自动重放另批，需审批面配合）。
- **不**给 `resume()` 加 replay 回调面（现状无回调即纯扫描，本条依赖此事实，不扩）。
- **不**新增 checkpoint `trace_ids` 消费面（仍只有 time-travel，跨进程撤销承 ADR-0136 既有局限）。
- **不**改 `scheduler.suspend/resume`（纯状态机转接，无持久化语义）。
- **不**在 `repl`/`app` 入口呈现（本 change 只接 `serve` + CLI `task` 两入口，面最小）。
