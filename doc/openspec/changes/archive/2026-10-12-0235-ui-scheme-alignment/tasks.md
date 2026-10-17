# Tasks 0235（回溯补建）

> 代码于 2026-10-12 由并行会话落地（commit `b42479b`）；本清单按 git 提交与现状代码补记。

## 1. 规格
- [x] 判定**规格中性**（`skip_specs: true`）：语义 delta 归 open 的 change `0233`；
      本 change 仅呈现材质（折叠符指示、去除 MAY 的缩略中间态、MAY 的耗时后缀、spinner 兜底、Web 标题表）

## 2. TUI（`src/core/ui/repl.py`）
- [x] 2.1 `_StepBlock` 去 `_STEP_TAIL_LINES` / `_full` / `step-more` ⇒ 展开即全文
- [x] 2.2 `_STEP_SYMBOLS` + `_step_symbol(kind)`：种类折叠符（仅作 `Collapsible` 指示符，不进标题）
- [x] 2.3 `_thinking_title(active, ms=…)` + 块内 `_started_at` ⇒ 落静 `Thinking · 1.2s`
- [x] 2.4 `_spin_defer_to_blocks()`：活动块出现后隐藏 spinner；审批期 `_spin_start("等待审批")` 重新拉起
- [x] 2.5 子任务折叠块标题去 `▸`；raw 产出块用 `⚠` 折叠符

## 3. Web（`frontend/`）
- [x] 3.1 新增 `src/lib/activity.js` 纯函数（标题 / 摘要 / 耗时 / 折叠符）
- [x] 3.2 `Chat.svelte`：统一 `timeline[]`；`loop.reasoning` 按 `round` 归并；`loop.result` 回 idle
- [x] 3.3 `TaskPanel.svelte`：里程碑复用 `actionTitle`，去 `▸` / `tool_id`

## 4. 文档
- [x] 4.1 `doc/03-interfaces/ui-scheme.md` 正式稿；根 `ui-scheme.md` 改指针

## 5. 测试
- [x] 5.1 `tests/test_repl.py`：`test_tui_step_block_expand_shows_full_text` /
      `test_tui_spinner_hides_when_activity_block_appears` / `test_tui_thinking_settle_appends_duration` /
      `test_step_symbols_differ_by_kind` / `test_tui_thinking_and_bash_use_distinct_collapse_symbols`
- [x] 5.2 `frontend/src/lib/activity.test.js`：`node --test`（提交时 9 passed）
- [x] 5.3 四门禁（提交时通过；本补记零代码改动，未重跑）

## 6. 归档
- [x] 6.1 `openspec validate`（本 change）
- [x] 6.2 归档至 `doc/openspec/changes/archive/`
- [x] 6.3 ADR-0225 / 台账 E172 / 测试节 §148（2026-10-17 与并行批次一并回填）
