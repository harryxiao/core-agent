# 设计 — trace 生命周期闭环与内存释放（change 0103）

## 0. 一句话

把「谁持有 trace 的事件、持有多久」**显式分区**：`Tracer` 只保有**在途**链路，**已完成**的留存归
**消费者**（进化 worker 取快照）；由此 `end_trace` 得以安全 `pop`，落盘真路径与内存有界**同时**成立。

## 1. 决策：责任分区（Tracer 只存在途），而不是把留存换个地方

**问题**：`end_trace` 必须 `pop` 才能止漏；但进化消费者是**延迟**读取的。两者直接冲突。

**备选**：

| 方案 | 评价 |
|---|---|
| (i) `end_trace` 只 emit 不 pop，由 worker 读后调 `discard` | 泄漏**搬到** worker；多一个 API 面与「调用方纪律」依赖 |
| (ii) Tracer 在 `end_trace` **直接推送** sink/observer | 「谁封口谁通知」更整齐，但**推翻刚发布的 0101 接线 + ADR-0094**（loop 的 `trace_observer` 要拆），内存特性与 (iii) **完全相同** ⇒ 纯审美收益 |
| (iii) 有界环形缓存（保留最近 N 条已完成） | 新增 `N` 旋钮 + 淘汰语义；N 只为测试而存在（evo 已走快照）⇒ **无生产消费者的可配性**，且制造内存 + 落盘**双真源** |
| **(iv) 责任分区：Tracer 只存**在途**；**留存归消费者**（采纳）** | `_events` 有界 = 在途链路数（真·有界）；消费者自持快照；**不新增 API 面、不推翻 0101** |

**采纳 (iv)**：`Tracer` 的 `_events` 语义收窄为 **in-flight only**，`end_trace` = `emit` + `pop`；
`EvolutionWorker.on_trace_complete` 在**回调时刻**（封口之前）取事件快照自持。

## 2. 顺序约束（本 change 最易错处）

loop 收尾顺序 SHALL 为：

```
记录全部遥测（含 loop_finished）
  → trace 完成回调 _notify_trace_complete(trace_id)   ← worker 在此取快照
  → tracer.end_trace(trace_id)                        ← 导出 + 释放
```

**若反序**（先 `end_trace` 再回调）：回调时 `_events` 已空 ⇒ `replay` 返回 `[]` ⇒
worker 的快照为空 ⇒ 进化证据链回退 `no_evidence`（**静默**，单测全绿）。故 loop 规格须写明该顺序，
并加回归守护用例。

## 3. 决策：`replay` 口径收窄为「在途」，已完成回溯走落盘（R1）

**问题**：`end_trace` 一 `pop`，「已完成任务仍可 `Tracer.replay`」就不再成立——而
`observability/spec.md`「链路追踪」原文与 3 处测试**正是这么用的**。

**取舍**：

- **R1（采纳）**：`replay` 服务**在途**链路；已完成任务的回溯以**落盘遥测**为真源。理由：
  ① 「回溯」的价值在于**事后复盘**，而这正是导出器（JSONL）存在的目的——本 change 干的就是**打通它**；
  ② 与本仓一贯的「不留双真源」口径一致（参见 phase-19 §E19 的裁决）；
  ③ 无任何用户面消费者（无 CLI / UI 读 `replay`），唯一读者是测试与 worker。
- **R2（不采纳）**：环形缓存保留最近 N 条 ⇒ spec 与测试不用改，但见 §1(iii) 的反对理由。

**受影响测试的迁移**：`test_three_event_kinds_logged`、`test_loop_*module_attribution`、
`test_phase13::test_loop_emits_trace_events` 由「封口后 `replay` 断言」改为「**注入捕获导出器**、
断言其收到的事件」——断言更强（证明落盘路径），且与 P0 的验收目标一致。

## 4. 决策：不改 evolution 的批触发语义，只在验收断言有界

`EvolutionTrigger(threshold=10)`（`engine.py:278-284`）要第 10 次 `maybe_run` 才真跑；
`worker.py:67` 的 `_completed.clear()` 只在**真跑之后**执行 ⇒ 期间 `_completed` 累积。这是**有意**的
批语义（攒够阈值再驱动一次 cycle），本 change **不改**。但因为 (iv) 让 `_completed` 从「id 列表」变为
「事件列表」，其内存曲线**变重**，故 P0 验收须包含**有界断言**（`_completed` 不随轮次无界增长、
受批窗口约束），避免「修了 Tracer、漏在 worker」。

## 5. 决策：`Exporter` 协议不增 `flush`

`BufferedExporter.emit` **内部已** `flush()`（`exporter.py:83-89`）；协议只有 `emit`（`exporter.py:22-25`），
多态上也调不到 `flush`。⇒ `end_trace` 只需 `exporter.emit(events)`，无需（也不应）单独 flush。
（订正 `phase-22.md` §2.2 步骤 4 的「→ flush」措辞。）
