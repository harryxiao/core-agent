# 0147 · TUI 流式回显合帧节流 + 表格整块延后渲染（账本 E89）

> 账本：`coding-plan/known-risk.md` **E89**（本轮新立）
> 规格面：`ui` MODIFIED「CLI 友好交互」（新增 Scenario「流式回显合帧与表格延后渲染」）
> ADR：**0139** ｜ 用户裁决：**A 合帧节流 + C 表格整块延后渲染**

## Why

用户反馈 TUI 流式回显「阶梯式、表格逐行绘制、不够丝滑」。定位**两条并列根因**（均在
`src/core/ui/repl.py`，**非** Markdown 控件缺陷）：

1. **逐 delta 全量重解析（阶梯抖动的根）**：`_show_delta`（`repl.py:463-489`）每收到一个
   SSE delta 就立即走 `_touch_tail` → `Markdown.update(text)`。Textual 的 `update()` 是
   **整篇 re-parse + 全量 re-layout**，且被 `Markdown.lock` **串行化** ⇒ 尾段越长每 delta
   代价越高（尾段 O(n²)），delta 密集时渲染队列积压 ⇒ 肉眼即「一卡一卡阶梯式」。
2. **未闭合表格逐行重排（表格抖动的根）**：change `0146` 已让表格**整块固化**（`_in_open_table`），
   但**未闭合期间**仍每 delta `_touch_tail` 重绘；Markdown 表格列宽**按内容自适应** ⇒ 每加一行
   整表列宽重算 ⇒ 表格区逐行「抽动」。

**对照参考（用户问「Claude 的如何丝滑」）**：Claude Code 的 TUI 是 **Ink（React for CLI）**：
`state → 虚拟树 → reconciler diff → 只重写变化的终端行（frame diffing）`，并**节流/合批**
渲染（非每 token 一次 paint）。本 change 只取其中**两条可直接落地的精髓**（**合帧节流** +
**整块延后渲染**），**不引入** React/diffing 运行时。

## What

全部为增量，既有语义逐字不动：

1. `repl.py` 新增常量 `_TAIL_FLUSH_S = 0.04`（尾段合并节拍）。
2. `_show_delta` 改为**仅入缓冲**（`_tail_buf`/`_live_buf` + `_tail_dirty`），懒启动
   `_tail_timer = self.set_interval(_TAIL_FLUSH_S, self._flush_tail)`（与 `_spin_timer` 同型）。
3. 新增 `_flush_tail()`：把**原 `_show_delta` 的分支体**（围栏 / 表格 / 常规）在合并后的缓冲上
   收口一次，**重入安全**（`_flushing`）+ **幂等**（`_tail_dirty`）。未闭合表格分支**改为延后
   返回**（不渲染，闭合或超 `_TAIL_TABLE_CAP` 后一次成型）。
4. `_add` 加**时序闸**：挂非尾 widget 前先 `_flush_tail()`（防重入），保证挂起尾段文本
   在动作行 / 思考块 / 审批提示 / barge-in 提示**之上**（时序不乱）。
5. `_flush_live` 增「停表 + 清脏」，**不调 `_flush_tail`**（避免双重渲染）；中断/异常仍不丢字。

## 影响

- **渲染次数与 delta 速率解耦**：尾段由「每 delta 一次」降为「每 40ms 至多一次 ⇒ 严格更少、
  更大的冻结块 ⇒ 布局抖动**严格减少**」。
- **表格一次成型**：未闭合表格不绘制中间态，列宽只算一次。
- **零回归**：围栏分支维持**流式可见**（不延后）；`_TAIL_SPLIT` 语义不变（只改在合并缓冲上
  求值）；`_touch_tail` / `_freeze_tail` / `_in_open_fence` / `_in_open_table` **逐字不动**。
- **有界 + 不丢字**：未闭合块超硬上限兜底固化；回复结束（含异常/中断）经 `_flush_live`
  最终固化挂起尾段（含被延后的未闭合表格）。

## 非目标（明确不做）

- **引入 React/Ink/diffing 运行时**：与「架构最优、不踩红线、尽量不依赖三方库」冲突；Textual
  自有布局/滚动，帧级 diff 无收益。
- **把 40ms 节拍做成配置项**：无需求、徒增配置面（YAGNI）。
- **表格中途占位符**：可选，本 change 不落，记为 ADR-0139 已知局限。
- **Web / APP 端**：`Chat.svelte` 以纯文本呈现（无渲染器），不适用本机制。

## 验证

- `.venv/bin/ruff check src tests` / `ruff format --check` 全绿；`pyright` **0/0/0**。
- `.venv/bin/pytest -q` ⇒ 基线 + 本 change 新增（`test_repl.py`：合帧 1 + 表格延后 1 + 围栏回归 1）；
  前两条**实现前红**、实现后绿；既有 repl/ui 用例全绿。
- `openspec validate --all` ⇒ 31 passed / 0 failed（归档后 30/0）。

## 风险与已知局限

- **未闭合长表格有「无可见进度」窗口**：> `_TAIL_TABLE_CAP`（8000）或流尽才显形；出路是加
  占位 `Static`，**不**回退 `_touch_tail`。记 ADR-0139 已知局限。
- **无 JS/前端面**：本 change 全 Python，四门禁即可覆盖。
