# Design 0268 — 失败回滚可见性

## D1 语义裁决：保留 trace 整轮回滚

既有规格「单轮回滚」承诺「逆序撤销该轮已产生的副作用，回到该轮开始前状态」。若缩窄为
「只撤销失败动作自身」，同一轮先前成功写入会保留，轮次进入**半完成**状态，与承诺冲突，也
让模型更难推理文件现状。故本 change 只增加**可见性**，不改回滚范围。

## D2 返回值与遥测

```python
def rollback(self, trace_id: str) -> RollbackReport | None:
    if self._tools is not None:
        return self._tools.rollback(trace_id)
    return None
```

提交循环（仅失败动作）：

```python
report = self.rollback(trace_id)
if report is not None and (report.reverted or report.undo_failed):
    self._trace(trace_id, "trace_rolled_back", {
        "reverted": len(report.reverted),
        "undo_failed": len(report.undo_failed),
    })
self._record_observation(ctx, action, result, rollback=report)
```

- 事件仅在**确有撤销或撤销失败**时发出；空报告不产生噪声。
- 走 `Tracer` 而非 `LoopEvent`：`astream` 的七类事件契约不变，消费方无需处理新类型。
- 载荷只有计数，不含 `EffectId`、路径、参数或错误正文（密钥/正文不进遥测）。

## D3 观察回灌

`_record_observation` 增加可选 `rollback` 参数：

```python
observation = {"error": result.error} if result.failed else {"data": result.data}
if rollback is not None and (rollback.reverted or rollback.undo_failed):
    observation["rollback"] = {
        "reverted": len(rollback.reverted),
        "undo_failed": len(rollback.undo_failed),
    }
```

- 键只在非空时出现 ⇒ 无效应可撤的失败保留既有 observation 逐字内容。
- 失败动作的 assistant/tool 消息序不变；回滚在 observation 回灌**之前**完成，模型看到的是
  回滚后的世界状态。
- 终止动作仍不写 observation（`is_terminal` 早退），但其失败触发的回滚仍产遥测。

## D4 撤销失败

`EffectTracker.rollback` 把 undo 抛错的效应留在 `_effects`（QUARANTINE）。本 change 只把
`undo_failed` 计数告知模型与遥测；不自动重试、不删除账目（人工介入语义不变）。
