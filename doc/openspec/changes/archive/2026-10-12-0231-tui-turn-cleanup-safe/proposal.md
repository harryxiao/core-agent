# Proposal 0231 — TUI 回合收尾异常安全化（change 甲）

## Why

2026-10-12 用户实跑：TUI 一轮结束后**永久停在「思考中…」、输入被吞**。只读取证（进程 727119 /
traces.jsonl / CPU / socket 快照）结论：该轮轮末维护性记忆调用超时（provider 缺省 `timeout=60.0` ×
`max_retries=3` ⇒ 4 次串行 60s ≈ 232s，尾部 08:49:17→08:53:09），期间 `_turn_busy=True` ⇒ 输入分发
一律拒绝并提示「处理中，请稍候（Ctrl+B 打断）」，**表现为卡死**（进程实际健康、事后自愈，无需 kill）。
该长等待本身由 change `0232`（`llm.timeout` / `llm.max_retries` 可配）治理。

由此暴露的**独立缺陷**：**回合收尾不异常安全**。

三个 turn runner 的 `finally` 把「可能抛错的**呈现**收尾」排在「**状态**复位」之前：

```python
finally:
    self._flush_live()      # ← 抛错则其后全部跳过
    self._spin_stop()       # ← 状态行残留（计时 timer 仍在跑）
    self._turn_busy = False  # ← 忙态**永不**复位 ⇒ UI 永久拒收输入
```

任一步抛错（瞬时取件 / 挂载 / 屏幕栈拆除期的渲染错误）都会**跳过忙态复位** ⇒
**一次瞬时错误 = UI 永久卡死**。同类缺口另有两处：`_spin_start(...)` 在 `try` **之外**（其失败无收尾）；
`on_input_submitted` 里 `_turn_busy = True` 之后的派发段（`run_worker` / 神兽入口）也在 `try` 之外。

## What Changes

- 新增私有 helper `_end_turn(*, flush_live=False)`：**先尽力收尾呈现**（`_flush_live` / `_spin_stop`
  各自**容错**，任一失败只降级、绝不外溢），**最后必定** `self._turn_busy = False`。
  **不吞**轮体异常（worker 崩溃语义不变）。
- 三个 runner（`_run_turn` / `_run_beast_turn` / `_run_task_turn`）的 `finally` 统一改调 `_end_turn(...)`；
  各自 `_spin_start(...)` 移入 `try`。
- `on_input_submitted` 忙态置位后的派发段包一层「异常 ⇒ 复位忙态 ⇒ 重新抛出」。

## Impact

- 影响模块：`src/core/ui/repl.py`（1 新 helper ＋ 3 runner ＋ 1 分发口）。
- **规格中性**（`skip_specs: true`）：`ui` spec **无**任何 Requirement 约束「收尾顺序 / 忙态复位」；
  忙态仅被**负向**引用（「忙碌中 SHALL 拒绝并提示等待」「切换 SHALL 仅在本轮执行结束之后发生」）。
  本 change **只恢复**「忙态 ⇔ 本轮在跑」这一**既有不变式**，不改任何被规格约束的面 ⇒ 零 spec delta。
- 零配置键、零三方依赖、零新暴露面；无异常时行为**逐字不变**。

## Migration

无需迁移。异常路径由「永久卡死」变为「收尾降级 + 忙态照常复位」。
