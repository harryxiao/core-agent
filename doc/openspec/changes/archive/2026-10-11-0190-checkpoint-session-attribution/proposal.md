# Change 0190 — 检查点会话归因 + task 路径会话接线

## Why

长任务（跨会话/持续轮次）场景下，任务级断点续跑链路上的**会话身份**存在三重不调和（2026-10-11
长任务评估取证）：

1. **检查点会话硬编码占位值**：`CheckpointFn` 回调签名无 session 形参
   （`src/core/orchestration/scheduler.py:32`）⇒ 组合根 `_write_checkpoint` 对每个检查点写死
   `"default"`（`src/core/runtime.py` `create_checkpoint(task_id, "default", …)`）。检查点的
   会话归属元数据**恒为谎言**，无从按会话寻址任务。
2. **CLI `task` 入口完全无会话身份**：`entry._task` → `_stream_task` → `orchestrator.astream`
   **不传** `session_id`（`src/core/entry.py`）⇒ 子任务轨迹 / 记忆 / 转录全部落入**全局未归属**
   （`scheduler.py` `_run_subtask` 空则不传第二实参）——与 REPL `/task`（发起会话归因）和 Web
   任务入口（同）行为不一致；同为任务入口，换个端进来归因就丢。
3. **续跑无法找回原会话**：`--resume` 重建计划与已完成集，但即便修复 ①②，续跑若另铸新会话，
   同一任务的轨迹将分裂在两个会话下。

结构根因是 ①（回调签名），②③ 是它在入口层的两个表现。

## What Changes

- **`orchestration`**：`CheckpointFn` / `DoneFn` 增第 4 参 `session_id: str`（两个调用点
  `scheduler.py` 波次收拢 / 终态处 session 均在作用域内）；组合根 `_write_checkpoint` 写入
  **实参原值**（空串照传 = 诚实的「无会话」，不再写占位值 `"default"`）。
- **`cli-ops` + `orchestration` 任务入口**：CLI `task` fresh 入口 SHALL 经**共享会话注册表**
  铸真会话（mode `"cli"`，同 `run` CLI 先例），并把该会话标识透传至 `orchestrator.astream`
  ⇒ 子任务轨迹 / 记忆 / 转录按该会话归因；`--resume` SHALL **复用检查点携带的发起会话标识**
  （同一任务续跑不分裂会话）；旧检查点（占位值 `"default"` / 无标识）SHALL 视作**未归属**
  （与既往行为逐字一致）并打印提示，不迁移旧数据。
- 规格变更：`orchestration`「断点续跑」（检查点携带发起会话标识条款）＋「任务入口与进度
  事件」（CLI task 会话铸/复用条款）；`cli-ops`「会话命令族与交互入口续聊」（一次性任务
  入口铸会话入同一注册表）。

## Impact

- **改动面**：`src/core/orchestration/scheduler.py`（类型别名 + 2 调用点）、`src/core/runtime.py`
  （检查点闭包）、`src/core/entry.py`（`_task` / `_stream_task`）；测试面 `test_orchestration.py`
  / `test_phase14.py` / `test_phase15.py` / `test_entry.py`（回调替身补第 4 参、resume 用例补
  `session_id` 元数据）。
- **零改动面**：REPL `/task` 与 Web 任务入口（`api.run_task` 已传 session，本 change 后其检查点
  自动获得真会话 —— 纯收益）；`durability` 存储层（`Checkpoint.session_id` 字段早已存在，只是
  从未被写真值）；子 Agent 循环 / 记忆 / 转录（消费方零改动，归因由生产方修正）。
- **兼容性**：旧检查点（`session_id="default"`）续跑视作未归属 —— 行为与既往 CLI task 逐字一致；
  不做数据迁移。

## Non-goals

- **不**做启动扫描呈现 / 崩溃恢复接线（change `0191`）。
- **不**给 CLI `task` 加 `--session` flag（显式指定会话属会话命令族面，无诉求）。
- **不**迁移既有 `"default"` 检查点数据（视作未归属即兼容）。
- **不**改 `scheduler.suspend/resume`（纯状态机转接，无持久化语义）。
- **不**新增 checkpoint `trace_ids` 消费面（仍只有 time-travel）。
