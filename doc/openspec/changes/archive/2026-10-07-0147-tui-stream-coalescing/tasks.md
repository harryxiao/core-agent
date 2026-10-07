# 0147 · 任务清单（TUI 流式回显合帧节流 + 表格整块延后渲染 / 账本 E89）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`ui` MODIFIED「CLI 友好交互」（新增 Scenario「流式回显合帧与表格延后渲染」）。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/ui/spec.md`：MODIFIED「CLI 友好交互」—— 新增 Scenario「流式回显合帧与表格延后渲染」+ 一段合帧/延后条文（既有 4 Scenario 逐字保留）
- [x] 1.2 `openspec validate 0147-tui-stream-coalescing` ⇒ valid；`validate --all` ⇒ 31 passed / 0 failed（归档后 30/0）
- [x] 1.3 ADR-0139（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 `tests/test_repl.py::test_show_delta_defers_until_flush`：delta 只入缓冲（`_tail_widget is None`）⇒ `_flush_tail()` 后方建 widget（实现前**红**）
- [x] 2.2 `tests/test_repl.py::test_open_table_not_rendered_until_closed`：未闭合表格 flush 后**不渲染**；空行闭合后恰 **1** 个 Markdown 块且解析为 `MarkdownTable`（实现前**红**）
- [x] 2.3 `tests/test_repl.py::test_open_fence_still_streams`：未闭合围栏 flush 后**仍渲染**（C 不误伤围栏）
- [x] 2.4 红态确认：2.1 / 2.2 在实现前**失败**，实现后转绿

## 3. 实现（`src/core/ui/repl.py`）

- [x] 3.1 常量 `_TAIL_FLUSH_S = 0.04`
- [x] 3.2 `__init__`：`_tail_timer` / `_tail_dirty` / `_flushing` 三字段
- [x] 3.3 `_show_delta` ⇒ 仅入缓冲 + 懒启动 `_tail_timer`
- [x] 3.4 新增 `_flush_tail()`（原分支体 + 重入闸 + 未闭合表格**延后返回**）
- [x] 3.5 `_add` ⇒ 时序闸（挂非尾 widget 前 `_flush_tail()`，防重入）
- [x] 3.6 `_flush_live` ⇒ 停表 + 清脏 + 保留既有 `_freeze_tail`（不调 `_flush_tail`）
- [x] 3.7 模块 docstring 补「增量合帧节流」一句；`_touch_tail`/`_freeze_tail`/判据/`_run_turn` 逐字不动

## 4. 文档同步

- [x] 4.1 `doc/03-interfaces/ui-interface.md`：TUI 渲染补「合帧节流 + 表格延后渲染、围栏流式可见」
- [x] 4.2 `doc/04-testing/test-cases.md`：§63（TC-SMOOTH，change 0147 / ADR-0139，账本 E89）＋ 手工项
- [x] 4.3 `coding-plan/known-risk.md`：§1 新增 E89（状态「已修」）＋ §3 ADR-0139 局限 ＋ §4 手工项

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 基线 1731 + 本 change 新增 3 = **1734 passed**
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical ⇒ `shutil.move` 至 `archive/2026-10-07-0147-tui-stream-coalescing/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md`（E89 登记）；ADR 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`fix(ui): TUI 流式回显合帧节流与表格整块延后渲染（change 0147）`
