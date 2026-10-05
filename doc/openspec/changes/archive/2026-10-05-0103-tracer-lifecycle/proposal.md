# 提案 — trace 生命周期闭环与内存释放（change 0103）

## Why

`coding-plan/phase-22.md` §2 的 P0（一手核实为真）：

1. **生命周期断裂**：`start_trace` / `end_trace` 全仓**零生产调用**——`loop/default.py:210` 用
   `trace_id = uuid.uuid4().hex` **自造 id** 绕过 `start_trace`；`JSONLExporter.emit` 只在 `end_trace`
   内部被触发（`tracer.py:39-43`）⇒ 生产**从不封口** ⇒ `traces.jsonl` 是**死路径**，「全链路日志」
   与「组合根装配生产导出器」两条规格要求**未被兑现**。
2. **内存泄漏**：`end_trace` 用 `self._events.get(trace_id, [])`（**不 pop**）⇒ 已封口 trace 的事件
   永久驻留；`record` 用 `setdefault().append()` 持续累积（`tracer.py:49-52`）⇒ `_events` 无界增长。

**关键耦合（本 change 的第一约束）**：组合根装配**单实例** `Tracer`（`runtime.py:235-238`），同时注入
loop 与 `EvolutionWorker`；`replay` 的**唯一生产调用点**是 `worker.py:85`（`_collect()`），而它是
**延迟**调用的——`on_trace_complete` 只登记 `trace_id`（`worker.py:51-53`），真正的 replay 发生在
**下一次冷路径** `maybe_run`。⇒ 本 change 若在收尾处直接 `pop`，会删掉延迟消费者尚未读取的事件、
**静默回退 change 0101/0102 的进化证据链**（诊断退回 `no_evidence`）。

## What Changes

- **`Tracer` 契约改为「只存在途」**（`observability/tracer.py`）：`start_trace` 建链、`record` 追加、
  `end_trace` = 交付导出器（落盘）+ **从内存移除**该链路事件。
- **`replay` 语义收窄为「在途」**：服务同进程内**未封口**链路；**已完成**任务的回溯以**落盘遥测**
  （导出器产出）为**真源**（R1 裁决：不留「内存 + 落盘」双真源，也不引入只为测试存在的环形缓存）。
- **loop 驱动生命周期**（`loop/default.py`）：开轮由注入的 tracer `start_trace()` 取回 `trace_id`
  （替换自造 uuid，缺省未注入则回退自造）；收尾在 **trace 完成回调之后**调用 `end_trace(trace_id)`
  **封口**。顺序 SHALL 为「记录全部遥测 → trace 完成回调 → end_trace」。
- **消费者侧留存**（`evolution/worker.py`）：`on_trace_complete` 由「登记 `trace_id`」改为「登记
  `self._tracer.replay(trace_id)` 的**事件快照**」（`_completed: list[list[TraceEvent]]`），
  `_collect` 遍历快照——**化解**「Tracer 只存在途」与「延迟消费」的冲突。
- **测试迁移**：3 处「跑完/封口后再 `replay`」的用例改为断言**导出器捕获到的事件**
  （顺带证明 P0 要打通的落盘真路径）。
- **文档**：observability 接口 §4/§5、ADR-0096、`test-cases.md` 追踪号。

## Non-goals

- **不引入有界环形缓存**（无生产消费者的可配性；且制造内存 + 落盘双真源）。
- **不改 evolution 批触发语义**：`EvolutionTrigger(threshold=10)` 保持；只在验收**断言**
  `_completed` 受批窗口约束、不随轮次无界增长（`worker.py:67` 的「只有真跑才清」为**有意**批语义）。
- **不做落盘回读**（JSONL reader / `trace show` CLI）——将来有真实需求时另开 change。
- **不碰** change 0101 的 `trace_observer` 接线与 ADR-0094，也不引入 Tracer→sink 推送（与 0101 接线重复）。
