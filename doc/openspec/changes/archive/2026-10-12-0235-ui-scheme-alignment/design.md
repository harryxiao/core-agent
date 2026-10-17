# Design 0235: UI 活动呈现对齐 ui-scheme

## 背景

`doc/03-interfaces/ui-scheme.md` 的共享时间线模型要求「TUI 与 Web 一套语义、分端材质」。
change `0233` 已落地 TUI 的**语义**（Thinking 缺省收起、友好标题、按 `round` 归并、撤回 Task 壳）；
本 change 把**材质**补齐到两端一致，并去掉 0233 遗留的中间态。

## 决策

- **D1 展开即全文，去掉缩略中间态**。0233 的「末尾有界行预览 ⇄ 全文」是 MAY；实际使用中
  「展开 → 只看末尾 8 行 → 再点正文 → 全文」多一次点击且易误判。改为点击标题即在**收起 ⇄ 全文**
  间切换，`_STEP_TAIL_LINES` / `_full` / `step-more` 一并删除。
- **D2 折叠符按种类区分，且只做指示符**。`_STEP_SYMBOLS` 映射活动种类 → 折叠符，注入
  `Collapsible(collapsed_symbol=…, expanded_symbol=…)` 同一符（不以 `▶/▼` 示意开合）。
  **不进标题文本** ⇒ 不与 0233「标题 SHALL NOT 以 `⏺`/`▸`/`└` 等作为主标识」冲突；未知种类
  退化为 `·`。
- **D3 Thinking 耗时用块内计时锚**。新块创建时记 `_started_at = time.monotonic()`，落静
  `_settle_one_thinking` 用 `_thinking_title(False, ms=…)` 生成 `Thinking · 1.2s`。耗时**不经
  事件载荷**（`loop.reasoning` 无 `duration_ms`），由呈现层自测；已落静（标题以 `Thinking · `
  开头）直接返回，幂等。工具块沿用既有 `_action_title(..., ms=…)`。
- **D4 spinner 让位与审批期重新拉起**。有活动步骤块后调用 `_spin_defer_to_blocks()`
  （`_spin_stop`）—— 标题已表达进度，spinner 仅兜底；审批挂起时无活动块可表达进度 ⇒
  `_spin_start("等待审批")` 重新拉起，结束后 `_spin_start("思考中")`（而非 `_spin_relabel`，
  因为 spinner 可能已停）。
- **D5 Web 抽零 DOM 纯函数**。`frontend/src/lib/activity.js` 只做标题/摘要/耗时/折叠符映射，
  与 `repl.py` 同口径；`Chat.svelte` 消费 `timeline[]`，`TaskPanel.svelte` 复用 `actionTitle`。
  用 Node 原生 `node --test`（仓内无 vitest）。
- **D6 规格中性**。语义 delta 唯一归 `0233`（open）；本 change 不写 spec delta —— 对同一
  Requirement 双写 delta 会在归档时互相覆盖（archive 脚本按 Requirement 全量替换）。

## 改动面

| 文件 | 改动 |
|---|---|
| `src/core/ui/repl.py` | `_STEP_SYMBOLS` / `_step_symbol` / `_thinking_title` / `_spin_defer_to_blocks`；`_StepBlock` 去三态；Thinking 计时锚；子任务标题去 `▸`；raw 块 `⚠` 符号 |
| `tests/test_repl.py` | 新增 4 例；更新步骤块 / Thinking / 子任务标题既有断言 |
| `frontend/src/lib/activity.js` + `activity.test.js` | 新增共享纯函数（10 个 `it`） |
| `frontend/src/views/Chat.svelte` | `lines` → `timeline[]`；`loop.reasoning` 按 round；`loop.result` 回 idle；工具块 |
| `frontend/src/views/TaskPanel.svelte` | 里程碑同标题表 |
| `doc/03-interfaces/ui-scheme.md`、`ui-scheme.md` | 正式稿 + 指针 |

## 测试与反证

本 change **无代码改动**（补记），测试锚点为 commit `b42479b` 已落地的用例：

- `test_tui_step_block_expand_shows_full_text`（展开即全文，替换原缩略窗口用例）；
- `test_tui_spinner_hides_when_activity_block_appears`（活动块后 spinner 隐藏；`hold` 住工具
  完成事件 ⇒ 在终态前断言）；
- `test_tui_thinking_settle_appends_duration`（`Thinking` / `Thinking · 12ms` / `Thinking · 1.5s`）；
- `test_step_symbols_differ_by_kind` / `test_tui_thinking_and_bash_use_distinct_collapse_symbols`
  （种类折叠符相异）；
- `test_tui_thinking_stream_merges_and_updates_in_place`（落静标题带耗时前缀）；
- `frontend/src/lib/activity.test.js`（`node --test`，提交记录 9 passed）。

回溯补记**未重跑反证**：代码未改动，上述用例为提交时已验收的承重锚。

## 局限

① UI 呈现材质属快速迭代面，`ui-scheme.md` 是**解释性**文档（非规格真源），后续调整不必逐条
走 change；② Web 侧 `node --test` 与 `npm run build` 不在四门禁内（Node 版本受环境限制，
构建未验）；③ 本记录为回溯补建 —— **提交时未留反证快照**，仅能引用既有测试；
④ 0233 仍 open（其 spec delta 待归档），本 change 的语义面正式规格以 0233 归档结果为准；
⑤ 并行批次 `0234` / `0236` / `0237` 同样缺 ADR / 台账 / 测试节条目（由并行会话收口），本补记
**不占用** ADR / `E` 编号，避免与其后续编号冲突。
