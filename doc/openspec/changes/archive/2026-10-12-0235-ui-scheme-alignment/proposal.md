# Proposal 0235: UI 活动呈现对齐 ui-scheme（TUI 种类折叠符 / Thinking 耗时 / Web 活动时间线）

> **回溯补建**：本 change 的代码已于 **2026-10-12** 由并行会话落地（commit `b42479b`，
> `feat(ui): 对齐 ui-scheme — 种类图标、Thinking 耗时、Web 活动时间线`），当时**未立 SDD 变更记录**。
> 本记录于 **2026-10-17** 依据 git 提交与现状代码补建；**零新增代码改动**，仅补齐归档账目。

## 为什么

`doc/03-interfaces/ui-scheme.md`（TUI / Web 一套活动呈现口径）落地后，两端呈现仍有分叉：

- TUI 步骤块展开后只显示**末尾 8 行**「缩略窗口」，需二次点击正文才看全文 —— 与「展开即全文」口径不符；
- 所有步骤块共用 `▶/▼` 折叠符，活动种类不可一眼区分；
- 有活动块时全局 spinner 仍在自转，标题与 spinner 争夺同一相位；
- Thinking 落静后只剩 `Thinking`，没有耗时，与工具块 ` · 1.2s` 口径不对称；
- Web Chat 仍是「思考串 + 行数组」，工具动作与 Thinking 没有统一时间线；TaskPanel 里程碑裸露
  `▸` / `tool_id`。

## 做什么

1. **TUI**（`src/core/ui/repl.py`）：
   - `_StepBlock` 去掉 `_STEP_TAIL_LINES` / `_full` / `step-more` 中间态 ⇒ **展开即全文**；
   - 新增 `_STEP_SYMBOLS` ＋ `_step_symbol(kind)`：折叠符按种类区分（Thinking `✦` / Bash `$` /
     Read `◇` / Write `✎` / Edit `✏` / Delete `⌫` / SubAgent `⊕` / Planner `▤` / WebFetch `◎` /
     Gate `☑` / Context `⊞` / raw `⚠` / subtask `◈`；未知退化为 `·`）—— 仅作为 `Collapsible` 的
     `collapsed_symbol` / `expanded_symbol`，**不进标题文本**（标题仍守 0233：无 `⏺` / `▸`）；
   - 新增 `_thinking_title(active, ms=…)`：落静 `Thinking` 可附 ` · 1.2s`（复用 `_fmt_ms`）；
     块内 `_started_at` 作为计时锚；
   - 新增 `_spin_defer_to_blocks()`：有活动步骤块后隐藏全局 spinner（标题优先，spinner 兜底）；
     审批期无活动块可表达进度 ⇒ `_spin_start("等待审批")` 重新拉起；
   - 子任务折叠块标题去掉 `▸`，折叠符用 `◈`；raw 产出块折叠符 `⚠`。
2. **Web**（`frontend/`）：
   - 新增纯函数 `src/lib/activity.js`（零 DOM）：`TOOL_NAMES` / `TARGET_FIELDS` / `STEP_SYMBOLS` /
     `toolName` / `toolTarget` / `actionTitle` / `titleFromAction` / `thinkingTitle` / `fmtMs` /
     `labeledTitle`，口径对齐 `repl.py`；
   - `Chat.svelte`：`lines` → 统一 `timeline[]`（`user | thinking | action | agent | raw`）；
     `loop.reasoning` 按 `round` 归并、落静带耗时；工具块缺省收起；`loop.result` 收口并把相位
     回 `idle`（状态条仅 busy 时「思考中…」）；
   - `TaskPanel.svelte`：里程碑用 `actionTitle`，去 `▸` 与裸露 `tool_id`。
3. **文档**：`doc/03-interfaces/ui-scheme.md` 正式稿（根目录 `ui-scheme.md` 改为指针）。

## 规格

**规格中性**（`skip_specs: true`）。理由：

- 本 change 的**语义**面（Thinking 缺省收起、友好标题、Thinking 不刷原文、Web 思考折叠）已由
  change `0233` 的 spec delta 承载（该 change 仍 open、未归档，delta 为真源）；
- 本 change 只改**呈现材质 / 实现细节**：折叠符是 `Collapsible` 指示符（标题文本不变）；
  去掉的「末尾缩略窗口」在 0233 delta 中本就是 **MAY**（「展开后若实现…」）；Thinking 耗时是
  0233 delta 允许的「完成态 MAY 追加短后缀」；spinner 兜底相位无 Requirement 约束；Web 标题表 /
  时间线为与 TUI 对齐的呈现材质。
- 若对同一 Requirement 再写一份 delta，归档时会与 open 的 `0233` delta **互相覆盖**（同一条
  MODIFIED）⇒ 语义 delta **唯一归 `0233`**。

## 影响

| 面 | 影响 |
|---|---|
| `src/core/ui/repl.py` | 展开即全文；种类折叠符；Thinking 耗时；spinner 让位；子任务标题去 `▸` |
| `frontend/src/lib/activity.js`（+ `activity.test.js`） | 新增共享标题纯函数（零 DOM） |
| `frontend/src/views/Chat.svelte` / `TaskPanel.svelte` | 统一时间线 + 相位；里程碑同标题表 |
| `doc/03-interfaces/ui-scheme.md` | 正式方案稿（TUI / Web 一套） |
| 测试 | `tests/test_repl.py`：4 新增（spinner 让位 / Thinking 耗时 / 种类折叠符 / 同屏异符）＋ 既有断言更新；`frontend/src/lib/activity.test.js`（`node --test`） |
| 显式不做 | 不做 Web 像素级复刻；不新建 SSE 事件面；不恢复末尾缩略窗口；不改 0233 的语义 delta（归 0233 归档）；`npm run build` 未验（Node `20.11.1` < Vite 8 要求 `^20.19 \|\| >=22.12`，环境问题，与 UI 改动无关） |
