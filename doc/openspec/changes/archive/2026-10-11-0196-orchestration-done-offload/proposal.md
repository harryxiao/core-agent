# Proposal 0196 — 任务完成回调卸载（orchestration-done-offload）

## Why（缺口）

`TaskScheduler` 在 `astream`（async generator）内**同步**调用完成回调：

```python
# src/core/orchestration/scheduler.py:290-292
self._state_machine.transition(task_id, TaskState.DONE)
if self._on_done is not None:
    self._on_done(task_id, outcomes, plan, session_id)   # ← 同步，跑在事件循环上
```

这本身在当前实现里**无症状**（`runtime._finalize` 只落一份检查点、廉价文件 IO）。但
**change 0197** 要在该回调里接**任务级 SOP 提炼**（一次**模型调用**）—— 一旦如此，就**精确复现**
**E103 / ADR-0157** 缺陷类：**事件循环上的同步模型调用**，会阻塞流式产出、拖垮同波次并发，且被
降级链静默吞掉（无留痕）。

⇒ 正确顺序是**先卸载，再接重活**（P3 局部化：0196 只改「回调在哪跑」，0197 只改「回调做什么」）。

**先例**：`src/core/loop/default.py:466-468` 已用 `await asyncio.to_thread(self._notify_turn, …)`
把每轮观察回调卸载出事件循环（change 0167 / ADR-0157）——本 change 把同一纪律补到编排收尾回路。

## What Changes

**规格先行**（`orchestration/spec.md`「异步执行单元契约」**MODIFIED**）：新增 bullet
「**收尾回路不阻塞**」+ Scenario「完成回调不阻塞事件循环」。

**实现**（`src/core/orchestration/scheduler.py`）：`DONE` 分支的 `self._on_done(...)` 改为
`await asyncio.to_thread(self._on_done, task_id, outcomes, plan, session_id)` ＋ `import asyncio`。

**调用时机与次数逐字不变**：仍在 `DONE` 达成后调用**一次**；检查点写入顺序、终态判定、
`task_finished` 事件语义**零改动**。

## Impact

- **规格**：`orchestration`（MODIFIED ×1「异步执行单元契约」+1 Scenario）。canonical `orchestration`
  scen **49 → 50**、req **11 不变**。
- **代码**：`scheduler.py` 一处调用点 + 一行 import。
- **测试**：+2 新增（回调在工作线程执行 / 回调内阻塞不阻塞事件循环）＋ 反证。
- **不做**：**不**卸载 `_checkpoint`（`scheduler.py:261-262`）—— 它只做既有廉价文件 IO、不承载
  模型调用，改它属超范围；**不**改回调签名与调用次数；**不**改终态 / 事件语义。

## Non-goals

- 任务级 SOP 提炼本身（change 0197）；质量门（change 0198）。
- `_checkpoint` 的卸载、`suspend`/`resume` 语义、并发度调整。
