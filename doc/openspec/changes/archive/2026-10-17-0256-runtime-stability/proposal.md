# Change 0256 — 运行稳定性：流式等待上限 / 中断留痕 / 压实进度（P0）

## Why

2026-10-17 会话 `cb37aba3ddf54bcc9336be2464c95c07` 的复盘（`~/.core/state` 的转录、
`traces.jsonl`、`memory.jsonl` 与 `conversations.json`）暴露三个运行稳定性缺口：

- **流式调用可无限挂起**：`StdlibLLMProvider.astream` 只在传输层读 socket 时有超时；若端点
  持续发送 SSE 注释 / keep-alive（`_iter_sse_payloads` 全部跳过、不入队），消费端
  `await queue.get()` **没有任何等待上限**，本轮永不结束。该会话的评审轮在 22:23 进入推理后
  静置数分钟，用户只能新开会话。
- **中断后证据全部丢失**：`Tracer` 只在 `end_trace` 时导出；`DefaultLoop.astream` 没有
  `try/finally`。消费方关闭 / 取消 / 异常时，本轮 `loop_started`、工具调用、压实等事件既
  不封口也不落盘 ⇒ 事后无法定位「卡在哪一步」。该会话最后一轮只留下压实写下的记忆条目，
  `traces.jsonl` 中没有任何本轮事件。
- **轮内压实静默阻塞**：压实含同步模型调用，实测单次 `memory_compact` 38 秒（该会话最后一次
  约 54 秒），期间事件流没有任何进度事件；且无总时长上限，慢端点可把一轮拖到数分钟。

P0 只修这三项（证据链 + 不再无限挂起 + 让用户看得见压缩）。P1 的「并行工具调用全执行 /
重复调用守卫 / `file_write` 原子写」另开 change。

## What Changes

- **流式增量等待上限**（`src/core/llm_provider/stdlib_provider.py`）：
  - `astream` 等待下一增量（含首块）施加 `timeout`（沿用构造注入的 `llm.timeout`，缺省 60 秒）；
  - 超时 ⇒ 归一 `LLMTimeoutError`，并尽力关闭底层响应以释放读线程；
  - 不重试流式调用（已外发的增量不可撤销），由 planner 既有 `LLMError` 分支产出失败终态，
    本轮正常收口。
- **流式中断留痕**（`src/core/loop/default.py`）：
  - `astream` 变为薄包装，内层执行体（原主循环）正常收尾时置完成标记；
  - 消费方提前关闭（`GeneratorExit`）/ 取消（`CancelledError`）/ 未收尾异常 ⇒ 先记一条
    `loop_aborted` 遥测（只含有界 `reason` 与轮次），再 `end_trace` **封口落盘**；
  - 正常轮次的事件序、封口时机（trace 回调之后）与 `collect_result` 的提前返回语义逐字不变。
- **轮内压实进度与上限**（`src/core/loop/default.py`、`src/core/ui/api.py`、`src/core/ui/repl.py`）：
  - 阈值压实前后各发一条事件：`loop.compacting`（`round`）与
    `loop.compacted`（`round` / `elapsed_ms` / `timeout`）；
  - 压实总时长缺省上限 **120 秒**（构造参 `compact_timeout` 可注入覆盖，`None` 关闭）；
    超时 ⇒ 记 `maintenance_failed(step="compaction_timeout")` 并**放行本轮**（fail-open），
    本轮不再重复压实；
  - 预算降级路径的压实复用同一上限；
  - TUI 把两条事件渲染为进度提示（Web/APP 忽略未知类型，行为不变）。

## 影响面

- 规格：`llm-provider` **ADDED** 1 req / 2 scen；`loop` **ADDED** 2 req / 5 scen。
- 代码：`src/core/llm_provider/stdlib_provider.py`、`src/core/loop/default.py`、
  `src/core/ui/api.py`、`src/core/ui/repl.py`。
- 测试：`tests/test_llm_provider.py`、`tests/test_loop.py`、
  `tests/test_loop_cost_observability.py`、`tests/test_ui.py`。
- 缺省行为：**有意变更**（属缺陷修复）—— 无增量的流式调用不再无限等待；异常/取消轮次会多
  一条 `loop_aborted` 遥测；压实会多两条事件并有 120 秒上限。正常路径的回复、事件序、
  记忆与转录语义不变。不新增配置键、不引入三方依赖。

## 不做

- **不做**流式重试（已外发内容不可撤销，重试会造成重复增量）。
- **不做**增量遥测落盘（每条事件即时写 `traces.jsonl`）—— 进程被强杀时仍会丢在途事件，
  登记为已知局限。
- **不做**压实线程的强制中止（Python 线程不可取消，超时后工作线程可能继续完成写入）；
  只做「本轮不再等待」，避免把静默阻塞变成无限阻塞。
- P1（并行工具调用全执行、重复调用守卫、`file_write` 原子写）不在本 change。
