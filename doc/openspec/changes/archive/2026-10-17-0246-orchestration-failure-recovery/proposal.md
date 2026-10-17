# Proposal — 编排失败恢复（change 0246）

## 为什么

只读盘点（`/tmp/orchestration-review.txt` P1-7）确认：`orchestration` 规格 R2 已承诺
「不推进下一步，回退重试（有限次）或重新规划」，实现却在**首个**子任务验收失败时
直接 `RECOVERING` + `task_failed` + `return`（`scheduler.py:243-252`）。`RECOVERING`
在状态机里**不是终态**，任务会永久悬置；目标未达标分支（`:282-289`）同型。另有两处
失败面未收口：

1. `_fan_out` 的 `asyncio.gather` 没有异常兜底（`scheduler.py:354-361`）——子 Agent
   抛出的异常会穿透 `astream`，消费方拿到裸异常而不是 `task_failed`。
2. 检查点没有恢复计数——即使实现重试/重拆，崩溃续跑后预算会重置，可能无限恢复。

## 改什么

- `TaskScheduler` 改为**恢复回路**（`while True` 包裹「执行计划 → 终态判定」）：
  1. 波次 fan-in 后只对**失败子任务**重试 1 次（已完成项不重跑）；
  2. 仍失败 → 重新拆解 1 次（保留原目标与已定成功标准；清空旧计划完成集/结果上下文）；
  3. 预算耗尽 → `FAILED`，错误码沿用最后一次失败原因。
- `_fan_out` 增加异常归一：`OrchestrationError` 保留原错误码，其余 `Exception` 归一为
  `SUBTASK_EXECUTION_FAILED`，`CancelledError` 透传。
- 空计划守卫：任何来源（检查点/planner）的 `plan.subtasks` 为空 → `task_failed`，
  不误判 `DONE`。
- `Plan` 增 `replans` 并随 `plan_to_dict`/`plan_from_dict` 往返；重拆前先写检查点。
- 事件：失败路径新增 `task_retrying` / `task_replanning`；`subtask_started` 增 `attempt`；
  `plan_ready` 增 `replan`。成功路径事件序列逐字不变。

## 影响面

- `src/core/orchestration/scheduler.py`（恢复回路、重试、重拆、事件、异常归一）
- `src/core/orchestration/models.py`（`Plan.replans` + 往返）
- 规格：`orchestration` R2 / R4 **MODIFIED**（+4 Scenario）
- 测试：`tests/test_orchestration.py`（恢复矩阵；两处既有失败基线有意更新）

## 不做

- 不加配置键：重试/重拆次数是固定策略（用户裁决：各 1 次）。
- 不新增错误码：终态错误码沿用最后一次失败原因，保调用方兼容。
- 不修取消/挂起/消费方断流/`on_done` 异常逃逸（D1 范围）。
- 不改 `exclude_source_prefixes=("beast.","pet")` 与任何会话隔离语义。
