# Proposal — TUI 退出不等待在途阻塞工作（Ctrl+Q 卡住）

## Why

**现象**（用户 2026-10-24 反馈）：TUI 里 Ctrl+Q 退出会卡住。

**实测复现**（pty 驱动真实/等价 app）：

| 场景 | Ctrl+Q 后进程退出耗时 |
|---|---|
| 空闲 | 0.27s（正常） |
| 在途 45s 阻塞默认执行器任务 | **42.4s**（= 在途工作剩余时长） |

**根因**：`run_repl` 走 `build_app(...).run()` → Textual `App.run()` → `asyncio.run(...)`。
`asyncio.run` 收尾调用 `loop.shutdown_default_executor(wait=True)`，**无限期 join 默认执行器
线程**；取消 Textual worker task 并不会中断线程本身。本轮在途工作恰好都跑在默认执行器上：

- **LLM 流式**：`stdlib_provider.astream` → `loop.run_in_executor(None, _produce)`，线程卡在
  socket 读上，最长拖到 `llm.timeout`（缺省 **60s**）；
- **工具执行**：`ToolProvider` → `asyncio.to_thread(tool.handler, ...)`（change 0265 已注明
  「不可取消」），`code_run` 前台子进程可能更久。

仓库已有同类认知（`loop/default.py::_run_offloaded`，change 0296）：压实/收尾为此改用**守护
线程**并明确注释「`asyncio.run` 收尾会 `shutdown_default_executor()` 并无限期等待卡住的
工作线程」。但该规避只覆盖压实路径，未覆盖 LLM 流与工具面。

**用户裁决**（2026-10-24）：采用**守护线程执行器**方案 —— 退出即放弃在途轮次（「停一轮」
仍用 Ctrl+B 打断，两者语义分离）。

## What Changes

- TUI 入口 `run_repl` 不再用 `App.run()` 的 `asyncio.run` 路径，改为：
  1. `asyncio.new_event_loop()` 自建循环；
  2. 装配**守护线程默认执行器** `_DaemonExecutor`（线程 daemon ⇒ 解释器退出不 join；
     `shutdown(wait=True)` 立即返回 ⇒ 循环收尾不等待）；
  3. `app.run(loop=loop)`（Textual 原生支持）；
  4. 收尾**有界**：取消残留任务 → `shutdown_asyncgens` → 关循环，**不**调
     `shutdown_default_executor`。
- 退出语义：Ctrl+Q 立即结束进程；在途 LLM 流 / 工具线程随进程终止（socket 由 OS 关闭）。
  既有取消语义不变：Textual 照常取消 worker、终端状态照常复原。
- 空闲路径、一轮正常完成后的退出行为**逐字不变**（本来就不等待）。

## Impact

- 规格：`ui` **ADDED ×1**（TUI 退出及时性）。
- 代码：仅 `src/core/ui/repl.py`（`_DaemonExecutor` / `_close_loop` / `run_repl`）。
  不改 `App` / 事件面 / 工具面 / LLM provider。
- 行为：退出及时性变化；其余（含 TUI 内一切呈现与命令）逐字不变。
- 配置：**零新配置键**；**零新依赖**。

## Out of Scope（明确不做）

- **不改全局 `asyncio.run` 调用点**（一次性 `run` / `serve` / `task`）：本轮只修 TUI 退出；
  其它入口的在途取消是否等待留作后续观察项。
- **不做「退出前优雅排空」开关**：不做 `ui.exit_wait` 之类的配置键；退出即放弃是唯一语义。
- **不改 LLM 流的可取消性**（不主动 close 响应、不改造 producer 线程）：由进程终止兜底。
- **不改 Ctrl+B 打断语义**：两者保持分离（Ctrl+B = 停本轮，Ctrl+Q = 退进程）。
- **不承诺已放弃线程的副作用完整**：退出瞬间被放弃的写操作可能只做了一半（`file_write`
  已原子化、记忆写入整文件写，风险面小但非零），记为已知局限。
