# 提案 — trace 收尾回调与模块归因（change 0101）

## Why

审计（`coding-plan/phase-21-findings.md`）发现进化引擎的 **plugin 维度整条接线未打通**，
其中**最先断裂的一环是 trace 通路本身**——两个缺陷叠加，使 `EvolutionWorker` 在生产**恒无输入**：

1. **冷路径拿不到任何 trace**：`EvolutionWorker.on_trace_complete`（`worker.py:51`）是全仓**唯一**的
   trace 完成登记入口，但它 **零生产调用方**（仅 `worker.py` 定义 + 测试调用）；loop 收尾只调
   `self._cold_path()`（`default.py:302-306`），而 `ColdPath = Callable[[], None]`（`default.py:43`）
   **不带 trace_id** ⇒ `_completed` 恒空 ⇒ `_collect()` 恒 `[]` ⇒ `maybe_run` 恒返回 `None`
   （`worker.py:61`）⇒ 进化冷路径在生产**永不运行**。
2. **trace 无模块归因**：`_to_traces`（`worker.py:88-114`）只认 `kind == "tool_call"`，且
   `plugin_id = tool or None`（`:112`）绑的是**工具名**（`tools.*` 命名空间）；`TraceEvent`
   （`events.py:12-20`）**无模块字段**、`kind` 词表（`:19`）**无「架构模块失败」通道** ⇒
   即便 trace 通了，loop 自身的失败（轮数/token 预算耗尽）也**无法归因到 `loop.default`**，
   `Diagnoser` 只能看到空表 ⇒ 归因转人工 ⇒ `no_evidence`。

本项只打通**归因接线**（补一个收尾回调 + 补一个可选字段 + 补一条适配通道），
**不新建 `PluginRegistry` 载体、不引入任何自动改架构代码的能力**（口径见 design.md §1）。

## What Changes

- **`TraceEvent` 增可选 `module_id: str | None = None`**（`observability/events.py`）——
  模块归因字段，缺省 `None`，既有构造点与序列化**逐字不动**。
- **loop 增收尾回调 `trace_observer`**（`loop/default.py`）——
  与既有 `ColdPath` 并列的新注入面，`TraceObserver = Callable[[str], None]`；在 `astream` 收尾、
  **本轮全部遥测事件记录完毕之后**按**轮**调用一次，**不受维护节拍节流**；异常降级留痕
  （`trace_observer_failed`）、不中断本轮；缺省未注入则不做。
- **loop 自身失败带模块归因**：`limit_reason` 非空时，`loop_finished` 遥测事件带
  `module_id="loop.default"`（`_trace` 增可选 `module_id` 形参）。
- **采集层增模块归因通道**（`evolution/worker.py`）——`_to_traces` 对**带 `module_id`** 的事件
  适配为 `Trace(plugin_id=module_id, …)`；既有 `tool_call` 通道**逐字不变**。
- **组合根接线**（`runtime.py`）——evolution 装配块内取 `trace_observer=evolution_worker.on_trace_complete`，
  注入主 loop；evolution 关闭时保持 `None`（**不为「未装配」造空转闭包**，同既有 `cold_path` 口径）。

## Non-goals

- **不把 13 个内部核心模块纳入 `PluginRegistry`**（口径与理由见 design.md §1；`runtime.py` 作用域内
  **没有 `registry` 变量**，纳入路线需先解决归属，且需给 5 个算法类补 `pass` 空转生命周期）。
- **不做工具级 trace**（`action_completed` 作为 `LoopEvent` 外发却未 `_trace`，工具调用无生产者）——
  转出账本（见 `coding-plan/phase-21.md` §1.4）。
- **不改诊断/提案/结晶语义**（kind 动态化与结晶结局诚实化在 change 0102）。
- **不改 `Diagnoser`**（它已能从 `t.plugin_id` 归因，`diagnoser.py:37-39`）。

## 风险

- **顺序敏感**：回调必须在**本轮全部遥测事件之后**调用，否则 `loop_finished` 的模块归因事件
  会被同轮冷路径 `maybe_run` 消费后 `_completed.clear()` 丢掉（`worker.py:67`）。
  测试须锁死「回调时事件已齐」。
- **语义面扩张**：`TraceEvent` 加字段属**兼容扩张**（dataclass 默认值），但须有测试证明
  **旧事件构造/序列化不变**（既有 4 种 `kind` 路径零影响）。
- **不节流的代价**：每轮一次回调会向 `_completed` 追加一条 trace_id；未达 `EvolutionTrigger`
  阈值时 `maybe_run` 直接返回 `None`（零模型调用），`_completed` 会缓慢累积到下次触发——
  这是**既定语义**（热路径只登记、不触发），但须在测试中确认「未达阈值不消费、不泄漏到结果」。
