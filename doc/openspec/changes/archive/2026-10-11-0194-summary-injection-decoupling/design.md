# Design 0194 — 摘要注入与历史回放解耦

## 1. 问题定位（P3）

| 面 | 事实 | 缺口 |
|---|---|---|
| `default.py:892` | `_load_summaries` 门控含 `self._history_turns <= 0` | 摘要通道被历史回放开关**连坐关闭** |
| `default.py:885` | 注释称「与 `_load_history` **完全同形**」 | **假** —— `_load_history` 受 `history_turns` 管是**本职**，摘要不是 |
| `loop/spec.md`「执行循环」 | Scenario「分层摘要作为独立系统块注入」**不带** `history_turns` 条件 | 实现**偏离**规格 |

## 2. 设计决策

### 2.1 门控删一项（最小外科手术）

```python
# 变更前
if (self._transcript is None or self._memory is None
        or not session_id or self._history_turns <= 0):
    return "", ""
# 变更后
if self._transcript is None or self._memory is None or not session_id:
    return "", ""
```

- **保留** `transcript is None` / `memory is None` / 空标识 —— 这是「摘要读取」的**本职**前置
  （摘要经 memory 取、转录是三层滑窗的载体），不在本 change 的解耦对象内。
- **删去** `self._history_turns <= 0` —— 该条件只属**历史回放**通道。

### 2.2 缺省行为逐字不变（兼容性红线）

`LoopConfig.history_turns` 缺省 `20 > 0` ⇒ `self._history_turns <= 0` **恒假** ⇒ 删去后门控**等价**。
仅在用户**显式**设 `loop.history_turns=0` 时行为改变（历史带空、摘要照进）—— 这正是修的对象。

### 2.3 与 `_load_history` 的边界

`_load_history`（`:906-914`）用 `plan.short_turns <= 0` 判空；`plan` 由 `_window_plan` 从
`history_turns` 算出（`history_turns=0` ⇒ `short_turns=max(0,0)=0`）⇒ 历史带**自然地**为空。
两条通道**各自**据其本职判据决定，**不再**经由 `_load_summaries` 的连坐。配额算法（`plan_window`
短 0.5 / 中 0.3 / 长 0.2）**零改动**。

## 3. 规格落点

`loop`「执行循环」**MODIFIED**：在「两层摘要……逐字一致。」之后补「两层摘要的注入 SHALL 与
历史回放开关**解耦**」条款 + Scenario「关闭历史回放仍注入摘要」。

## 4. 验证

- 红测试：`history_turns=0` ⇒ 摘要块仍在（红：变更前 `("", "")`）；`history_turns>0` 逐字回归；
  `history_turns=0` 历史带确为空原文；docstring 不再称「完全同形」。
- 四门禁（直连二进制）；`openspec validate` → 手工归档（0 行丢失 / 0 Scenario 标题丢失）。
