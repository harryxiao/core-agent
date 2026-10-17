# Design — 运行中取消与消费方断流（change 0249）

## D1 取消信号与在途打断

调度器维护两个任务级登记表（进程内，终态释放）：

```python
self._cancel_events: dict[str, asyncio.Event] = {}
self._wave_tasks: dict[str, asyncio.Task[list[SubtaskOutcome]]] = {}
```

`cancel(task_id)`：

1. 终态（`DONE` / `FAILED`）⇒ **直接返回**（幂等，不重置 tracker）。
2. `self._cancel_events.setdefault(task_id, asyncio.Event()).set()`。
3. 当前波次的 fan-out 任务未完成 ⇒ `cancel()`（打断在途子任务）。
4. 非终态 ⇒ 转 `FAILED`，`tracker.reset(task_id)`，`_results.pop(task_id)`。

`cancel` 不新增线程/锁：调度器与取消调用方在同一事件循环（既有 `suspend`/`resume` 同口径）。

## D2 执行流观察取消

`astream` 拆为**薄包装 + `_stream_task`**（原主管线）：

```python
async def astream(...):
    try:
        async for event in self._stream_task(...):
            yield event
    finally:
        self._release(task_id)
```

`_stream_task` 在以下检查点观察取消信号（命中即 `yield self._cancelled(task_id)` 并返回）：

- 拆解完成后（初始 / 重拆前）；
- 每个波次 `_execute_wave` 返回后（波内取消由 `_stream_wave` 安静收拢）。

`_execute_wave` 在 `_stream_wave` 返回后同样短路，**不**做 `VERIFYING` 转移（取消已把状态
置 `FAILED`，避免非法转移）。

取消终态事件 `task_failed` 的 `code = TASK_CANCELLED`，**不重复**状态转移（由 `cancel` 完成）。

## D3 fan-out 回收

`_stream_wave`：

- `gather_task` 注册进 `_wave_tasks[task_id]`，`finally` 中 pop。
- 正常路径 `await gather_task`；`CancelledError` 时若取消信号已置（协作取消）⇒ 安静收拢，
  否则透传（外部取消不被吞）。
- `finally`：未完成 ⇒ `cancel()`；以 `suppress(CancelledError, Exception)` 回收
  （清理边界不重复抛出已观测异常）。

`_fan_out` 既有 `finally: emit(None)` 在取消路径解除队列阻塞，排水循环随之收口。

## D4 终态释放

`_release(task_id)`（`astream` 的 `finally`）：pop 取消信号与在途任务登记、pop `_results`；
状态非终态（消费方断流 / 外部异常）⇒ 转 `FAILED`、`tracker.reset`、trace
`task_aborted`。正常 `DONE` / `FAILED` 路径只做缓存释放，不动 tracker 与状态。

## D5 错误码

`OrchestrationErrorCode.TASK_CANCELLED = "TASK_CANCELLED"`：仅用于取消终态事件与 `run()`
抛错，与 `SUBTASK_TIMEOUT`（子任务级）区分。
