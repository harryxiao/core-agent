# Tasks — 0300 TUI 行距节奏

## 1. 规格与测试先行

- [x] 1.1 `specs/ui/spec.md` MODIFIED「TUI 视觉密度预算」（重写 Markdown 预算段 + 2 Scenario）
- [x] 1.2 `tests/test_repl.py` 新增 4 用例（段落 0 空行 / 列表 1 行每项 / 小节前 0 / 章前后各 1）
- [x] 1.3 确认新增用例先红（实现前）：3 红 1 绿（TC-RHYTHM-04 当前已满足，作 H1 回滚守卫）

## 2. 实现（`src/core/ui/repl.py` CSS）

- [x] 2.1 `MarkdownParagraph { margin: 0 }`
- [x] 2.2 `MarkdownBulletList, MarkdownOrderedList { margin: 0 }`
- [x] 2.3 `MarkdownH1 { margin: 1 0 1 0 }`；`MarkdownH2…H6 { margin: 0 }`

## 3. 门禁与文档

- [x] 3.1 `uv run ruff check src tests` / `ruff format --check src tests` / `uv run pyright`（全绿）
- [x] 3.2 `uv run pytest -q`（全量全绿 **3393 passed**）
- [x] 3.3 反证（`cp` + `md5sum`）：段落 margin 回 1 ⇒ 2 红 / H2 回 1 ⇒ 1 红 / H1 回 1 ⇒ 1 红；复原 `md5sum` 一致
- [x] 3.4 `cd doc/openspec && openspec validate --all`（32/0，归档前）
- [x] 3.5 `ui-scheme.md` §5.1 密度表；ADR-0290 / known-risk E236 / test-cases §213
- [ ] 3.6 归档 / 提交（**待用户确认**）
