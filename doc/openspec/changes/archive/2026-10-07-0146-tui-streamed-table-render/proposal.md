# 0146 · TUI 流式 Markdown 表格整块解析（账本 E88）

> 账本：`coding-plan/known-risk.md` **E88**（本轮新立，持续登记簿）
> 规格面：`ui` MODIFIED「CLI 友好交互」（新增 Scenario「流式结构化块整体解析」）
> ADR：**0138** ｜ 用户裁决：**bearing change**（`ui` 规格先行）

## Why

TUI 流式回复中的 **Markdown 表格**渲染为竖线原文，而非表格（`E88`）。根因**不在** Markdown
控件（`src/core/ui/repl.py:214-219` 用 Textual `Markdown`，v8.2.8 内建表格渲染），而在**流式
按行固化**的分段策略：

- `_show_delta`（`repl.py:461-479`）在 `len(text) >= _TAIL_SPLIT` **或 `text.endswith("\n")`**
  时立即 `_freeze_tail`，把尾段固化为**独立** Markdown 块（append-only，之后不再重渲染）。
- Markdown 表格必须**整块**（表头行 + `|---|` 分隔行 + 数据行，中间无空行）才能被解析；而逐行
  流式时每行 delta 都以 `\n` 结尾 ⇒ **表头行一到达就被固化**为只有表头、无分隔行的独立块 ⇒
  解析器判为普通段落；后续分隔行、数据行各自固化为新的独立块 ⇒ 表格永拼不齐 ⇒ 用户见竖线原文。
- 代码**已**对**代码围栏**做了同类保护（`_in_open_fence`，`repl.py:481-485`，`_TAIL_FENCE_CAP`
  兜底），**唯独没覆盖表格** —— 属机制疏漏：表格与围栏同属「须跨行整体解析」的结构。

## What

**只补表格分支，既有语义逐字不动**（全部为增量）：

1. `repl.py` 新增常量 `_TAIL_TABLE_CAP = 8000`（与 `_TAIL_FENCE_CAP` 同口径）。
2. `_show_delta` 在**围栏分支之后、常规分支之前**插入**表格分支**（与围栏同型）：未闭合表格块
   内**延后**固化（仅超硬上限兜底）。
3. 新增静态方法 `_in_open_table(text)`：自尾向前取**当前块**（连续非空行，遇空行即止；忽略
   行终止用的单个尾 `\n`），当且仅当**每行都含 ≥2 个 `|`** 时判为「未闭合表格块」。
   **围栏判定优先于表格**（围栏内 `|` 不作表格）。
4. **不触** `_TAIL_SPLIT` 常规路径与 `_freeze_tail` / `_touch_tail` / `_flush_live` 语义 ⇒
   非表格场景**零回归**。

## 影响

- **零回归**：表格分支只在「当前块每行 ≥2 个 `|`」时生效；普通回复（无竖线）走既有常规路径，
  行为与缺省**逐字一致**；代码围栏路径因**优先序**（围栏先判）**完全不受影响**。
- **内存有界**：未闭合表格块超 `_TAIL_TABLE_CAP` 兜底固化，与围栏同口径。

## 非目标（明确不做）

- **Web 端 Markdown 渲染**：`frontend/src/views/Chat.svelte` 以**纯文本** `{line.text}` 呈现
  （无 markdown 渲染器），表格在 Web 恒显竖线原文 —— 那是「无渲染器」而非分段 bug，属**另桩
  更大特性**，不在本 change。
- **列表 / 引用块等其它跨行结构**：本次只对齐用户点名且与围栏**机制同源**的**表格**。

## 验证

- `.venv/bin/ruff check src tests` / `ruff format --check` 全绿；`pyright` **0/0/0**。
- `.venv/bin/pytest -q` ⇒ 基线 **1729** + 本 change 新增（`test_repl.py`：判据 1 + 集成 1）；
  集成用例**修复前红**（逐行固化成多块）、修复后绿（单块）。
- `openspec validate --all` ⇒ 31 passed / 0 failed（delta 并入既有 `ui` spec、cap 目录数不变）。

## 风险与已知局限

- **判据近似**：散文行含 ≥2 个 `|`（如 `a | b | c`）会**过度延后**固化（有界，超硬上限兜底）；
  极罕见，记 ADR-0138 已知局限。
- **无 JS/前端面**：本 change 全 Python，四门禁即可覆盖。
