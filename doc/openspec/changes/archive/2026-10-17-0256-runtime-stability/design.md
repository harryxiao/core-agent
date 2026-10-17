# Design 0256 — 运行稳定性三项

## D1 流式增量等待上限：按「下一增量」计时，不设总时长

`astream` 的消费循环改为：

```python
item = await asyncio.wait_for(queue.get(), timeout=self._timeout)
```

- **为什么是队列等待**：传输层 socket 超时只约束「单次 read」。端点持续发 SSE 注释
  （`: ping`）或空帧时，read 不断返回、socket 超时不触发，而 `_iter_sse_payloads` 不产出
  任何 payload ⇒ 队列永远没有新元素。对队列等待加限才能覆盖这种「连接活着但模型不产出」。
- **为什么不设总时长**：长回复 / 推理模型可能持续产出数分钟；总时长会误杀正常长输出。
  这里约束的是**相邻增量的最大间隔**（含首块），产出持续即视为健康。
- **超时归一**：`asyncio.TimeoutError`（3.11 起即内建 `TimeoutError`）→ `LLMTimeoutError`；
  planner 既有 `except LLMError` 分支产出失败终态（`LLM 调用失败: …`），本轮正常收口。
- **不重试**：流式已外发的增量不可撤销；重试会让消费方看到重复/乱序正文。断流的部分内容
  保留（既有语义），随后抛错。
- **资源释放**：生产者线程把响应对象登记到 holder；消费端超时时尽力 `close()`，避免读线程
  继续挂在长连接上（线程本身不可取消，仍可能阻塞到下一次 read 超时——登记为局限）。

## D2 中断留痕：包装 `astream`，只做 `loop_aborted` + 封口

原 `astream` 主体整体改名为 `_astream_events(user_input, trace_id, *, session_id, state)`；
公开 `astream` 成为薄包装：

```python
trace_id = self._start_trace(user_input)
state = {"finished": False}
reason = "interrupted"
try:
    async with contextlib.aclosing(self._astream_events(...)) as events:
        async for event in events:
            yield event
except BaseException as exc:
    reason = type(exc).__name__
    raise
finally:
    if not state["finished"]:
        self._trace(trace_id, "loop_aborted", {"reason": reason})
        self._end_trace(trace_id)
```

- **完成标记由执行体置位**（正常收尾在 `_end_trace` 之后、`state["finished"] = True`）：
  不能以「是否见过 `loop_finished` 事件」判定——执行体在 `loop_finished` 之前已调用
  `_notify_trace_complete` 与 `_end_trace`，消费方若在 `reply_delta` 就停下，会误判为中断。
- **正常路径不改封口时机**：执行体仍在 `trace_observer` 之后 `end_trace`，`collect_result`
  在 `loop_finished` 提前返回时本轮 trace 已封口（既有测试守护）。
- **异常路径**：`BaseException`（含 `CancelledError` / `GeneratorExit`）重抛，先留痕后封口；
  不写转录、不写记忆、不改轮末检查点（中断轮不应伪装成完成轮）。
- **`aclosing`**：确保包装器被关闭时内层执行体也收到关闭，避免挂起的 planner 生成器滞留。
- **载荷有界**：`{"reason": <类名或 interrupted>}`，不含用户文本 / 异常消息 / 密钥。

## D3 压实进度与上限：事件可见，超时放行

- 阈值压实调用点：
  ```python
  yield LoopEvent("loop.compacting", {"round": ctx.rounds})
  elapsed_ms, timed_out = await self._compact_bounded(ctx, trace_id)
  yield LoopEvent("loop.compacted", {"round": ..., "elapsed_ms": ..., "timeout": ...})
  ```
- `_compact_bounded` 把 `asyncio.to_thread(self._compact, ...)` 包进
  `asyncio.wait_for(..., timeout=self._compact_timeout)`；超时记
  `maintenance_failed(step="compaction_timeout")` 并返回 `(elapsed_ms, True)`。
- **缺省 120 秒**：实测正常压实 38 秒；120 秒给慢端点留余量，同时把「数分钟静默」截断。
  构造参 `compact_timeout` 可注入（测试用 0.05；`None` 关闭上限）。
- **fail-open**：超时后本轮继续（`compacted=True`，不重复压实）；记忆固化可能未完成，
  但这是**降级**而不是错误——与 `_compact` 内既有「单步失败不中断本轮」同语义。
- **线程不可取消**：`wait_for` 只取消等待，工作线程可能继续写完；记忆写回是追加型、
  既有维护节拍本就与下一轮并发，故不新增一致性假设。登记为局限。
- 预算降级路径复用同一上限（它同样阻塞本轮）。

## D4 UI 映射

`_EVENT_MAP` 显式登记两条事件（该表是 LoopEvent → SSE 类型的唯一契约面）；TUI
`_format_event` 渲染单行提示：

- `loop.compacting` → `上下文压缩中…`
- `loop.compacted` → `上下文已压缩（<ms>ms）`，超时追加「（超时放行）」

Web/APP 对未知类型忽略，无需改动。

## 局限（登记）

1. 强制杀进程（SIGKILL / 终端直接关闭）时 `finally` 不执行，在途事件仍会丢；增量落盘另行提案。
2. 压实超时后工作线程继续运行，可能与后续记忆写入交错；只保证本轮不再等待。
3. 流式超时不重试；端点若反复「有心跳无内容」，表现为每轮一次失败终态，而非自动恢复。
4. 流式超时依赖 `llm.timeout`（缺省 60 秒）；慢首块的推理模型可能被误判，需按部署调大。
