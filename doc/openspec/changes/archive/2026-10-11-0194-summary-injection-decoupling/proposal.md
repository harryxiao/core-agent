# Proposal 0194 — 摘要注入与历史回放解耦

## Why（缺口）

`DefaultLoop._load_summaries`（`src/core/loop/default.py:882-894`）的门控把**摘要通道**与
**历史回放开关**连坐：

```python
if (self._transcript is None or self._memory is None
        or not session_id or self._history_turns <= 0):
    return "", ""
```

`loop.history_turns` 的语义是**历史回放的轮数上界**（`plan_window(self._history_turns, …)`），
与「该会话的两层摘要是否注入」**无干** —— 规格里二者本就是**两条独立通道**（`loop/spec.md`
「执行入口组装请求时注入分层摘要」的 Scenario「分层摘要作为独立系统块注入」**不带** `history_turns`
条件）。但实现把 `history_turns <= 0` 塞进摘要闸 ⇒ 用户一旦把 `loop.history_turns` 设为 `0`
（关闭历史原文回放，常见于「只要摘要不要原文」的长任务省 token 配置），**摘要也被静默关掉** ⇒
长任务的记忆注入**整条消失**，且**无任何留痕**（长任务失忆的又一隐蔽来源）。

**取证**：`_load_summaries` 与 `_load_history` gate「完全同形」的注释（`:885`）是**假的**
—— `_load_history` 该不该受 `history_turns` 管是**它的本职**（`:914` 用 `plan.short_turns`），
而 `plan` 由 `_window_plan` 从 `history_turns` 算出；摘要通道**不该**受此连坐。

## What Changes

**规格先行**（`loop/spec.md`「执行循环」**MODIFIED**）：显式写入「两层摘要注入与历史回放开关
**解耦**」条款 + Scenario「关闭历史回放仍注入摘要」。

**实现**（`src/core/loop/default.py`）：`_load_summaries` 的门控**删去** `self._history_turns <= 0`
一项 ⇒ 剩 `transcript is None / memory is None / 空标识` 三项（与「摘要读取需要转录与记忆已注入、
且会话标识非空」的本职判据一致）。

**缺省行为逐字不变**：`loop.history_turns` 缺省 `20 > 0` ⇒ 该条件恒假 ⇒ 门控等价 ⇒ 逐字回归。

## Impact

- **规格**：`loop`（MODIFIED ×1「执行循环」+1 Scenario）。canonical `loop` scen **77 → 78**、
  **6 req 不变**。
- **代码**：`_load_summaries` 门控删一项 + docstring 诚实化（「与 `_load_history` 完全同形」
  改为「**不**受历史回放开关连坐」）。`_load_history` / `_window_plan` / `plan_window` **零改动**。
- **测试**：+4 新增（`history_turns=0` 摘要仍注入；`history_turns>0` 回归逐字不变；
  `history_turns=0` 历史带确为空；docstring 断言）。
- **不做**：`_load_summaries` 对「转录未注入」的依赖保留（摘要读取当前经 `self._transcript`
  存在性作前置，属既有设计；本 change 只解耦 `history_turns`）；三层滑窗配额算法 / `plan_window` /
  预算记账 **零改动**。
