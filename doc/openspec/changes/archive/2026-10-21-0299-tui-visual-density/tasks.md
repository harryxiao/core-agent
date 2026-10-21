# Tasks — 0299 TUI 视觉密度改版

## 1. 规格与测试先行

- [x] 1.1 写 `specs/ui/spec.md` ADDED「TUI 视觉密度预算」
- [x] 1.2 `tests/test_repl.py` 新增密度用例组：chrome 预算 / 展开体无顶空行 / 围栏高度 /
      截断上界 / 元信息行 / 高亮冒烟 / 欢迎横幅 / 轮次分隔
- [x] 1.3 确认新增用例先红（实现前）

## 2. 密度实现（`src/core/ui/repl.py` CSS + compose）

- [x] 2.1 状态行合并：`#hints` 去边框高 1 行；`#spinner` 移入 `#status` 行；footer 预算 4/5
- [x] 2.2 `Collapsible > Contents { padding: 0 0 0 2; }`
- [x] 2.3 Markdown 密度覆盖（`Markdown` padding / 围栏 / H1–H6 / 水平线）
- [x] 2.4 `.welcome` 去边框（5→2 行）；`#palette` max-height 8→6
- [x] 2.5 轮次分隔 `turn-sep`（`_run_turn` finally + CSS）

## 3. 文件呈现（`_StepBlock` + `_add_action_widget`）

- [x] 3.1 `_LEXERS_BY_SUFFIX` + `_render_tool_output`（write/patch/read 三路，容错回退灰显）
- [x] 3.2 `_StepBlock.set_code(code, meta, lexer)`：`.step-meta` 首行 + `Syntax` 正文 +
      `_MAX_BODY_LINES=40` 截断尾行
- [x] 3.3 完成分支按工具接线；非文件工具逐字不变

## 4. 门禁与文档

- [x] 4.1 `uv run ruff check src tests` / `ruff format --check src tests` / `uv run pyright`
- [x] 4.2 `uv run pytest -q`（基线 3380 全绿 + 新增全绿）
- [x] 4.3 反证（`cp` 到 `/tmp` + `md5sum` 复原）：去围栏覆盖 / 去截断 / 恢复 `#hints` 边框
- [x] 4.4 `cd doc/openspec && openspec validate --all`
- [x] 4.5 `doc/03-interfaces/ui-scheme.md` §4 + §5.1 重写；ADR-0289 / known-risk E235 /
      test-cases §212
- [ ] 4.6 归档 / 提交（**待用户确认**）
