# Design: action_started / action_completed 事件

## 发射点

`DefaultLoop.astream` 主循环内 `result = await self.act(action, trace_id, approved=...)`
前后包夹：

```
if not action.is_terminal:            # 终止动作（空 tool_id）不发——它不是工具调用
    yield LoopEvent("action_started", {"round": ctx.rounds, "tool_id": ..., "args": 节选})
t0 = time.monotonic()
result = await self.act(...)
if not action.is_terminal:
    yield LoopEvent("action_completed", {"round": ctx.rounds, "tool_id": ...,
        "ok": not result.failed, "duration_ms": int((monotonic()-t0)*1000),
        "output": 节选(result.data or result.error)})
```

## 载荷

| 字段 | 类型 | 说明 |
|---|---|---|
| round | int | 当前回合（与 step_completed 对齐） |
| tool_id | str | 工具 id（如 `tools.code_run`） |
| args | dict/str | action_started：args 序列化节选（≤400 字符） |
| ok | bool | action_completed：`not result.failed` |
| duration_ms | int | action_completed：monotonic 差 |
| output | str | action_completed：`result.data`/`result.error` str 化节选（≤400 字符） |

## 取舍

- **不发 action args 全量**：事件面有界（对齐 reply_delta 只发增量的惯例），
  全量参数经 trace 审计可查，UI 折叠区展示节选足够。
- **审批拒绝也发 action_completed(ok=false)**：拒绝即结果（fail-closed），
  UI 动作行能落 ✗ 收尾而不是永久挂起。
- **终止动作不发**：空 tool_id 的 Action 是"本轮结束"信号，非工具执行，
  语义上属于 reply 阶段。
