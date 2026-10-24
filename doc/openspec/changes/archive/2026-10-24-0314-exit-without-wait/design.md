# Design — TUI 退出不等待在途阻塞工作（0314）

## 1. 目标与不变量

**目标**：Ctrl+Q 的退出耗时**不随在途阻塞工作的剩余时长增长**；在途 LLM 流 / 工具线程随
进程终止，不被 join。

**不变量**：

1. 空闲退出与既有行为一致（终端复原、退出码 0）。
2. TUI 内的呈现、命令、审批、事件处理**逐字不变**（本 change 不碰 app 类体）。
3. 一轮正常完成后退出：结果与既有一致（线程本已结束，无行为差异）。
4. Ctrl+B 打断语义不变；Ctrl+Q 不新增确认。
5. 零新配置键、零新第三方依赖。

## 2. 根因链

```
run_repl → build_app(...).run() → Textual App.run() → asyncio.run(run_app())
                                                     └─ Runner.close()
                                                        ├─ _cancel_all_tasks()
                                                        ├─ loop.shutdown_asyncgens()
                                                        └─ loop.shutdown_default_executor(wait=True)
                                                           └─ join 默认执行器线程   ← 卡在这里
```

取消 worker task 只停**等待方**；生产者线程（`run_in_executor` / `asyncio.to_thread`）继续
执行到函数返回。LLM 流式生产线程阻塞在 socket 读上（≤ `llm.timeout`），`code_run` 前台子进程
可能更久 ⇒ 退出耗时 = 在途工作剩余时长。

实测（45s 阻塞线程）：空闲 0.27s；在途 **42.4s**。

## 3. 方案

### 3.1 守护线程默认执行器

```python
class _DaemonExecutor(Executor):
    """退出友好的默认执行器：守护线程 + 不 join 的 shutdown。"""

    def submit(self, fn, /, *args, **kwargs):
        if self._closed:
            raise RuntimeError("cannot schedule new futures after shutdown")
        future: Future = Future()
        def runner() -> None:
            if not future.set_running_or_notify_cancel():
                return
            try:
                future.set_result(fn(*args, **kwargs))
            except BaseException as exc:  # noqa: BLE001 — 原样转交调用方
                future.set_exception(exc)
        threading.Thread(target=runner, daemon=True).start()
        return future

    def shutdown(self, wait=True, *, cancel_futures=False):
        self._closed = True
```

- **线程为 daemon**：解释器退出时 `concurrent.futures.thread._python_exit` 只 join 其自建
  （非 daemon）线程 ⇒ 不阻塞。
- **`shutdown(wait=True)` 立即返回**：即使有代码调 `loop.shutdown_default_executor()` 也不等待。
  （本 change 的 `run_repl` 收尾本来就不调它，双保险。）
- 取消语义：Future 一旦提交即启动线程，无「未启动队列」；`cancel_futures` 无实际作用，
  文档注明。

### 3.2 入口改造（`run_repl`）

```python
def run_repl(api, session_id=""):
    app = build_app(api, session_id)
    loop = asyncio.new_event_loop()
    loop.set_default_executor(_DaemonExecutor())
    try:
        asyncio.set_event_loop(loop)
        app.run(loop=loop)          # Textual 原生支持外部 loop
    finally:
        _close_loop(loop)           # 取消残留任务 + shutdown_asyncgens + close（不 join 执行器）
        asyncio.set_event_loop(None)
```

`_close_loop` 复刻 `asyncio.run` 的**取消**部分、**省略**执行器 join：

1. `asyncio.all_tasks(loop)` 全取消并 `gather(return_exceptions=True)` —— 与
   `_cancel_all_tasks` 同口径（Textual 已取消 workers，这里兜底其它残留任务）；
2. `shutdown_asyncgens()`（**不** `shutdown_default_executor()`）；
3. `loop.close()`。

被取消任务若在等默认执行器 Future：取消立即完成（线程继续在后台，随进程终止）。

### 3.3 为什么不用其它方案

| 方案 | 否决理由 |
|---|---|
| 全仓把 `to_thread` / `run_in_executor` 换成 `_run_offloaded` 式守护线程 | 改动面覆盖 provider / tools / hooks / worktrees 十余处；执行器层一处收口等价 |
| 退出时主动 close LLM 响应 / kill 子进程 | 需从 app 到 provider 的取消链路，且覆盖不全（hooks / worktrees / gate） |
| `os._exit(0)` | 跳过 `atexit`（hooks `close`、MCP 子进程回收、插件卸载）⇒ 泄漏子进程 |
| 退出前优雅排空（配置等待上限） | 用户裁决「退出即放弃」；新增配置键违背「零新配置键」 |

## 4. 测试策略

- **执行器单测**：结果交付 / 异常转交 / `shutdown` 后拒绝提交 / `shutdown(wait=True)` 对在途
  任务**立即返回**（用 `threading.Event` 卡住 worker，断言 `shutdown` 耗时 < 0.5s）。
- **入口单测**（monkeypatch `build_app`）：假 app 的 `run(loop=...)` 断言
  `loop.get_default_executor()` 为 `_DaemonExecutor`；在假 app 内起一个阻塞执行器任务后返回，
  断言 `run_repl` 在 1s 内返回（对照：旧实现会等到事件 / 线程结束）。
- **反证**：① 把 `_DaemonExecutor` 换回默认执行器 ⇒ 入口用例超时红；② `shutdown` 改为 join
  worker ⇒ 执行器用例红；③ `run_repl` 换回 `app.run()` ⇒ 入口用例红（假 app 收到 `loop=None`）。

## 5. 已知局限

- 退出瞬间被放弃的线程可能只做了一半（写文件 / 落记忆）：`file_write` 已原子化（change 0257），
  记忆为整文件写，但仍是「非正常终止」风险。
- 只修 TUI（`repl`）；一次性 `run` / `serve` / `task` 的在途取消仍走 `asyncio.run` 收尾。
- 线程随进程终止，不执行 `finally` 清理（如关闭 HTTP 响应对象）—— 由 OS 回收 socket。
