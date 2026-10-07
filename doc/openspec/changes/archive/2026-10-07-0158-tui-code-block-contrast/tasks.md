# 0158 · 任务清单（TUI 代码块背景可辨识）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`ui` **MODIFIED**「CLI 友好交互」（代码块可辨识：背景不透明 + 对比度 ≥ 2.0 + 1 Scenario）。
> 状态：**已归档**（2026-10-07；四门禁全绿，`openspec validate --all` 30/0）。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/ui/spec.md`（delta，MODIFIED）：「CLI 友好交互」补「代码块 SHALL 与正文可辨识」+ Scenario
- [x] 1.2 ADR-0150（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 `tests/test_repl.py`：新增「代码块背景不透明 + 与主背景对比度 ≥ 2.0」用例（实现前红 ⇒ 1.02）
- [x] 2.2 红态确认：默认 `black 10%` 在 `#121212` 上合成 `#101010`，对比度 ≈ 1.02 ⇒ 必红

## 3. 实现

- [x] 3.1 `src/core/ui/repl.py`：`ReplApp.CSS` 新增 `MarkdownFence { background: $surface-lighten-3; }`

## 4. 文档同步

- [x] 4.1 `doc/03-interfaces/ui-interface.md` §2：补代码块可辨识口径
- [x] 4.2 `doc/04-testing/test-cases.md`：新增 `## 73.`（TC-CODEBG）
- [x] 4.3 `coding-plan/known-risk.md`：E98 行补「后续 0158 收敛视觉层」＋ §3 加 ADR-0150 局限行

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 全绿（含本 change 新增用例）
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical（ui）⇒ 移至 `archive/2026-10-07-0158-tui-code-block-contrast/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md`（E98 后续）；ADR-0150 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`fix(ui): TUI 代码块背景可辨识（不透明 + 明度差），深色底上不再等同正文（change 0158）`
