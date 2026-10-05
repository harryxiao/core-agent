# 设计 — trace 收尾回调与模块归因（change 0101）

## 1. 口径裁决：信号走既有 trace 通道，不新建载体

原稿（`phase-21.md` 旧版 §5.1/§5.2）曾计划「在 `PluginRegistry` 上加质量信号接口 + `registry.promote`」。
**废止**，理由（逐条一手核实）：

| 依据 | 事实 |
|---|---|
| 作用域不存在 | `PluginRegistry` 全仓只在 `PluginInstaller` 内**默认构造**（`installable.py:93`）；`runtime.py:396` 连 `registry=` 都不传 ⇒ 组合根**没有 `registry` 变量**，原稿写法会直接 `NameError` |
| 无真实生产者 | `FAULTED` 状态只在 `_load_inline` / `_load_with_timeout` / `unload` 失败时产生（`registry.py:118-164`）；内部模块**不经注册表加载** ⇒ 「失败记信号」仍要在真实失败点插桩 |
| 买不到验收 | 本 change 的每条验收（信号可归因、事件带模块）用 trace 通道 **1 个字段 + 1 条通道**即可达；纳入注册表需给 `evolution.{collector,diagnoser,evaluator,validator,worker}` 5 个零 `generation/schema/coeffects` 的类补 plugin 形状，`load/unload` 只能 `pass` 空转（**ADR-0054 明确拒绝过的形态**） |
| 诊断已就绪 | `Diagnoser.diagnose` 本就按 `t.plugin_id` 逐条计分（`diagnoser.py:37-39`）⇒ **不需要新载体**，缺的是**生产端的模块归因事件** |

**结论**：本 change 只做「补收尾回调（让 trace 流进 worker）+ 补模块归因字段（让 loop 失败可归因）」。

## 2. 回调注入面：为什么是 `TraceObserver` 而不是复用 `cold_path`

`ColdPath = Callable[[], None]`（`default.py:43`）**不带 trace_id**，无法让 worker 知道「哪条 trace 完成了」。
若把 trace_id 塞进 `cold_path`，会把**两个不同节律**混在一个回调里：

| 维度 | 冷路径机会（既有） | trace 完成登记（新增） |
|---|---|---|
| 节律 | `maintenance_interval` **节流**（缺省 900s） | **每轮**（不节流） |
| 语义 | 「跑一轮进化 cycle」 | 「登记一条已完成的 trace」（`worker.py:51` 既定语义：**只登记、不触发、不阻塞**） |
| 缺省 | 未注入 ⇒ 不做 | 未注入 ⇒ 不做 |

若合并：`EvolutionTrigger` 的「累计 N 条 trace」会退化成「累计 N 个 interval」，冷路径的触发语义被节拍侵蚀。
故**新增并列回调面**，`cold_path` **不动**。

`loop` **不 import evolution**（架构红线，与 `TurnObserver` / `ColdPath` 同款），生产侧在组合根注入闭包
（此处直接给 bound method `evolution_worker.on_trace_complete`，**不需要闭包包装**）。

## 3. 调用位置与顺序（顺序敏感）

`astream` 收尾现状（`default.py:265-272`）：

```
self.remember(trace_id, [...], session_id=session_id)
self._maintain(trace_id)                      # ①记忆遗忘 ②cold_path（节流）
self._trace(trace_id, "loop_finished", {"reply": …, "failed": bool(limit_reason)})
if not streamed: yield LoopEvent("reply_delta", …)
yield LoopEvent("loop_finished", LoopResult(…))
```

**回调插在 `_trace(loop_finished)` 之后**：

```
self._trace(trace_id, "loop_finished", {…}, module_id="loop.default" if limit_reason else None)
self._notify_trace_complete(trace_id)         # ← 新增：本轮遥测已齐，登记
```

**为什么必须在本轮全部 `_trace` 之后**：`_maintain` 在本行**之前**执行，若把回调放在它之前，
worker 会在同轮 `maybe_run → _collect → replay` 中消费本 trace，而**此刻 `loop_finished` 尚未记录**
⇒ 同轮 `_completed.clear()`（`worker.py:67`）之后该事件**永不再被采集**。放在最后 ⇒ 本 trace 进入
`_completed`，由**下一次**冷路径机会（下一拍或 `evolve run`）消费，事件完整。

`_maintain` 与新增回调**互不影响**：前者管「机会」，后者管「登记」，两者各自降级。

## 4. 模块归因字段：一个字段、两条通道

```
TraceEvent.module_id: str | None = None      # 归因对象所属的架构模块 id（缺省 None）
```

- **谁写**：loop 在**自身失败**时对自己的 `loop_finished` 事件写 `module_id="loop.default"`。
  （未来其他模块可在自己的失败点写，本 change 只接 `loop.default` 一处，其余按需。）
- **谁读**：`EvolutionWorker._to_traces` 对带 `module_id` 的事件产出
  `Trace(plugin_id=module_id, task_type="module_health", action={"event": kind}, result=payload,
  success=not payload.get("failed", False))`。
- **兼容性**：dataclass 默认值 ⇒ 既有 4 种 `kind`（`model_io`/`tool_call`/`effect`/`metric`）路径
  **零改动**；`kind` 词表**不扩**（`module_id` 与 `kind` 正交：前者是「谁」，后者是「什么事」）。

**命名空间口径**：`plugin_id` 的语义是**「归因对象 id」**——既可能是工具 id（`tools.*`），
也可能是 13 个内部核心模块 id（`loop.default` 等）。两套命名空间**永不相交**（已核实工具 id 全部形如
`tools.*`），故可在同一字段共存而不歧义；文档串须写明。

## 5. 组合根接线

```
evolution_worker = EvolutionWorker(tracer=tracer, engine=evolution_engine, trigger=EvolutionTrigger())
evolution = evolution_worker
trace_observer = evolution_worker.on_trace_complete     # ← 新增
…
loop = DefaultLoop(…, trace_observer=trace_observer, …)
```

`evolution` 关闭时 `trace_observer` 保持 `None` ⇒ 不注入、不造闭包（同 `cold_path` 既有权衡）。
**只注入主 loop**（子 agent / 神兽 / 宠物 loop 不注入）：它们的失败不属本轮 evolution 覆盖范围，
且避免同一 `_completed` 被多 loop 并发追加（**无锁列表**）。

## 6. 测试计划

| 用例 | 断言 |
|---|---|
| 回调按轮提交 | 注入回调 + 跑一轮 ⇒ 回调调用 1 次、收到非空 trace_id |
| 回调时事件已齐 | 回调内 `tracer.replay(trace_id)` ⇒ 含 `loop_finished` |
| 不受维护节拍节流 | `maintenance_interval` 设很大（未达间隔）⇒ 回调仍被调用 1 次 |
| 回调失败降级 | 回调抛错 ⇒ `run` 正常返回、`replay` 含 `trace_observer_failed` |
| 未注入则不做 | `trace_observer=None` ⇒ 无副作用、无 `trace_observer_failed` |
| 模块归因写入 | `limit_reason="LOOP_LIMIT_EXCEEDED"` 那轮 ⇒ `loop_finished` 事件 `module_id=="loop.default"` |
| 正常轮无归因 | 正常收尾 ⇒ `loop_finished.module_id is None` |
| 事件兼容 | 既有 `tool_call` / `model_io` 构造与序列化**逐字不变** |
| 采集适配 | 带 `module_id` 的失败事件 ⇒ `Trace.plugin_id == module_id`、`success is False` |
| 既有通道不变 | `tool_call` 事件 ⇒ 仍产出 `task_type="tool_use"`、`plugin_id == tool` |
| 组合根装配 | `build_runtime`（fake planner，不出网）⇒ 主 loop 的回调**是** `worker.on_trace_complete` |
| 关闭时无注入 | `evolution` 关闭 ⇒ 主 loop 该回调为 `None` |
