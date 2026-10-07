# 0146 · 任务清单（TUI 流式 Markdown 表格整块解析 / 账本 E88）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`ui` MODIFIED「CLI 友好交互」（新增 Scenario「流式结构化块整体解析」）。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/ui/spec.md`：MODIFIED「CLI 友好交互」—— 新增 Scenario「流式结构化块整体解析」（表格与围栏同理须整块固化，既有 3 Scenario 逐字保留）
- [x] 1.2 `openspec validate 0146-tui-streamed-table-render` ⇒ valid；`validate --all` ⇒ 31 passed / 0 failed（归档后 30/0）
- [x] 1.3 ADR-0138（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 `tests/test_repl.py::test_in_open_table_predicate`：判据纯函数 —— 表头后半开 `True`；表格后接**空行** ⇒ `False`；表格后**紧接散文行** ⇒ `False`；**代码围栏内**不误判；散文行仅含单个 `|` ⇒ `False`
- [x] 2.2 `tests/test_repl.py::test_streamed_table_renders_in_single_block`：桩 loop 逐行 emit 表格各行 ⇒ `#timeline` 内该回复为**单个** `Markdown` 块（修复前多块 ⇒ 红），其 `source` 含完整表头+分隔+数据行
- [x] 2.3 红态确认：2.2 在实现前**失败**（逐行固化，`assert 4 == 1`），实现后转绿

## 3. 实现

- [x] 3.1 `src/core/ui/repl.py`：常量 `_TAIL_TABLE_CAP = 8000`（＋ `_TABLE_MIN_PIPES = 2`）
- [x] 3.2 `src/core/ui/repl.py::_show_delta`：围栏分支之后插入**表格分支**（同型：未闭合延后、超上限兜底）
- [x] 3.3 `src/core/ui/repl.py::_in_open_table`：静态方法（当前块每行 ≥2 个 `|` ⇒ 未闭合表格）
- [x] 3.4 **围栏优先序**：`_in_open_fence` 先判（围栏内 `|` 不作表格）；常规路径逐字不动

## 4. 文档同步

- [x] 4.1 `doc/03-interfaces/ui-interface.md`：TUI 渲染补「流式结构化块整体解析、块闭合方恢复固化」
- [x] 4.2 `doc/04-testing/test-cases.md`：§62（TC-TABLE，change 0146 / ADR-0138，账本 E88）＋ 手工项
- [x] 4.3 `coding-plan/known-risk.md`：新建（三合一登记簿）＋ E88 状态「已修（change 0146 / ADR-0138）」

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ 354 files already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 1729 + 本 change 新增 2 = **1731 passed**
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical ⇒ `shutil.move` 至 `archive/2026-10-07-0146-tui-streamed-table-render/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md`（E88 登记）；ADR 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`fix(ui): TUI 流式 Markdown 表格整块解析（change 0146）`
