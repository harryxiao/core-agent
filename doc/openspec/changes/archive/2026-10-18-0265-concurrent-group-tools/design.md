# Design 0265 — 组内工具并发执行

## D1 并发资格：coeffect 只读判定

```python
_CONCURRENT_DENY_TOKENS = ("write", "spawn", "outbound")

def _is_concurrent_safe(action, tools) -> bool:
    if action.is_terminal or tools is None:
        return False
    for definition in tools.active_tools():
        if definition.tool_id == action.tool_id:
            return not any(
                token in coeffect
                for coeffect in definition.coeffects
                for token in _CONCURRENT_DENY_TOKENS
            )
    return False
```

- 只认**声明**（coeffects），不认工具名 / handler 形态：`file_read`（`filesystem:read`）、
  `process`（`process:read`）、`context_read`（`[]`）可并发；`file_write` / `file_patch`
  （`filesystem:write`）、`code_run` / `gate_run`（`process:spawn`）、`web_fetch`
  （`network:outbound`）、未知工具一律不并发。
- 空 coeffects 视为只读（如 `context_read`）；判定 fail-closed：找不到定义即不并发。

## D2 批次边界：连续只读段 + 写屏障

循环取到当前动作后，仅当**当前动作本身**可并发、无去重命中、且键未出现过时，才向后吸收
`pending` 中**连续**的可并发动作：

- 遇到不可并发动作（写 / 副作用 / 终止）**停止吸收**，该动作留在 `pending`，下一轮单独串行执行；
- 遇到重复键停止吸收（重复动作需要前一个的**已提交结果**才能复用，留到后续迭代走
  `batch` 去重）；
- 吸收上限 = `max_rounds - ctx.rounds`（不越过轮次剩余额度）。
- 吸收后逐个做中间件 / 确认门（顺序执行；确认门可能含人工审批）；若中间件把某个动作变成
  终止或副作用动作，整批退化为**串行执行**（仍按原序提交）。

## D3 执行与提交分离

- **执行**：并发段先按原序发出全部 `action_started`（`round = ctx.rounds + i`），
  `asyncio.gather` 各调 `self._act(...)`（保留 `act_wrapper` 重试链；每个协程独立设置
  `current_session_id` ContextVar）。串行段沿用「开始 → await → 完成」。
- **提交**：无论并发或串行，结果按**原序**逐个提交：`action_completed` → 观察者
  （熔断记账）→ 观测回灌 → 失败回滚 → `observe`（轮次 +1 / reply 终态）→ `step_completed`
  → 压实阈值 → token 预算。压实与预算判定在整段提交完成后执行一次（同一批次语义）。
- 只读段不产生效应，故并发执行不影响撤销栈顺序；串行段的写动作仍逐次记录效应。
- 终止动作 / 单动作 / `concurrent_reads=False` 时事件序与观测逐字不变。

## D4 同步 handler 卸载

```python
async def _call(self, tool, args):
    if inspect.iscoroutinefunction(tool.handler):
        return await tool.handler(**args)
    result = await asyncio.to_thread(tool.handler, **args)
    if inspect.isawaitable(result):
        result = await result
    return result
```

- 同步 handler 在工作线程执行 ⇒ 多个 `ainvoke` 真并发，且普通调用也不再阻塞事件循环。
- `asyncio.wait_for` 超时只停止等待，**不能**终止已进入的工作线程（Python 线程不可取消）——
  与既有协程 handler 超时语义的差异记录为已知局限；写类工具超时上界 30s，实际 handler 为
  本地短操作。
- 效应记录（`tracker.record` / `tool.undo()`）仍在事件循环线程、在 handler 返回后执行，
  `EffectTracker` 自带 `RLock`。
