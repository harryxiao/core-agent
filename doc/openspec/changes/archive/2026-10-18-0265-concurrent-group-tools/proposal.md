# Proposal 0265 — 组内工具并发执行

## Why

`ActionGroup`（原生并行 `tool_calls`）目前**逐个串行**执行：模型一次请求多个独立只读动作
（读三个文件、查多个后台任务）时，总耗时等于各动作耗时之和。同时 `ToolProvider._call` 在
事件循环线程上直接调用**同步** handler，即使经 `asyncio.gather` 发起也无法重叠（事件循环被
阻塞），「真并发」只在协程 handler 上成立。

## What Changes

- **只读动作并发**：动作组内连续的、工具 coeffects 不含 `write` / `spawn` / `outbound` 词元的
  非终止动作（且去重键互不相同）以 `asyncio.gather` 并发执行；写 / 有副作用 / 未知工具动作保持
  串行，并作为并发批次之间的**屏障**（保证写序与撤销快照序）。
- **同步 handler 卸载到工作线程**：`ToolProvider._call` 对非协程 handler 经
  `asyncio.to_thread` 执行，协程 handler 仍在事件循环上 await；外层 `wait_for` 超时语义不变。
- **提交仍按原序**：`action_started` 按原顺序在启动前发出；`action_completed` / `step_completed`
  / 观测回灌 / 回滚 / 压实与预算判定按动作原顺序提交，事件载荷键集不变。
- **开关**：`DefaultLoop(concurrent_reads=True)` 构造参数；置 `False` 时逐字回到串行路径。
  纯读时无——并发批次不越过 `max_rounds` 剩余额度；单动作路径逐字不变。

## Impact

- `src/core/loop/default.py`、`src/core/tools/provider.py`。
- 规格：`loop` **MODIFIED**「单次推理多工具动作」；`tool-use` **MODIFIED**「异步工具调用」。
- 测试：新增 `tests/test_concurrent_group_tools.py`；既有 `tests/test_parallel_tool_calls.py`
  断言保持。
- 文档：`doc/02-modules/{loop,tool-use}.md`、`doc/03-interfaces/tool-use-interface.md`、
  `doc/04-testing/test-cases.md`、ADR / 台账。

## 不做（明确边界）

- 不并发写动作（文件写 / code_run / 安装 / 进程终止等一律串行屏障）。
- 不做跨轮次调度或工作池；并发仅限同一 `ActionGroup` 内的连续只读段。
- 工作线程超时后不可强制终止（Python 线程限制），仅返回 `TIMEOUT`；记录为已知局限。
