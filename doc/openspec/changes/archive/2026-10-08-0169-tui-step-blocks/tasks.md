# 0169 · 任务清单

> 触发：用户 2026-10-08 实测 TUI（思考不可见 / 步骤看不出在干什么 / 长行不折行），
> 四项诉求经 AskUserQuestion 裁决为：思考块与工具块**缺省展开缩略**、标题 = 友好名 + 目标、
> 点正文展开全文 / 点标题收起（三态）；子任务块**本轮不改**。

## 1. 规格与决策（先行）

- [x] 1.1 `specs/ui/spec.md` **MODIFIED** Requirement「思考过程回显（Think）」：缺省形态**分端**
       （TUI 缩略 / Web + APP 逐字保留收起）；既有 2 Scenario 逐字保留 + 1 条改写（名保留，Validator
       拒改名 —— MODIFIED 块须含既有全部 Scenario）
- [x] 1.2 `specs/ui/spec.md` **ADDED** Requirement「TUI 步骤块（缩略 / 全文 / 收起）」+ 6 Scenario
- [x] 1.3 **ADR-0160**（子类化而非新造 / 三态物理落点 / 末尾窗口必须 Python 切片 / 白名单目标摘要 /
       折行用 `.step-body` 而**不复用** `.hint` / `format_action_event` 逐字不动 / append-only 消 O(n²) /
       「折叠块展示」相容的解释 / 手势的 Textual 实证 / 5 项局限）+ 变更追踪行
- [x] 1.4 `openspec validate 2026-10-08-0169-tui-step-blocks` ⇒ **valid**

## 2. 测试先行（红）

- [x] 2.1 `_tool_target` 表驱动：`path`（Read/Write/Edit）/ `url` / `script` / `gate` / `pointer`、
       未知工具 ⇒ `""`、缺字段 ⇒ `""`、`args` 非映射（str）⇒ `""`、超长截断加 `…`、多行只取首行、
       空白值 ⇒ `""`
- [x] 2.2 缩略窗口：喂 20 行 ⇒ 正文只呈现末尾 `_STEP_TAIL_LINES`(8) 行 + 「还有 12 行」提示
- [x] 2.3 点正文展开全文并回缩（缩略 ⇄ 全文）
- [x] 2.4 点标题收起 / 再展开（收起 ⇄ 展开，缺省缩略）
- [x] 2.5 正文含远超视口的单行 ⇒ 折行呈现（守护 `.step-body` 的 `width: 1fr`，防退回裁切）
- [x] 2.6 思考增量实时追加且**同一轮归并同一块**（喂多段 ⇒ 只有 1 个步骤块，正文含全部文本）
- [x] 2.7 工具块标题**带目标**且**不含正文参数**（含 `content` 一类必须不出现）
- [x] 2.8 改既有断言：`test_tui_action_widget_lifecycle`（缺省已展开 + 标题带目标）与
       `test_tui_thinking_renders_in_single_collapsed_block`（缺省缩略态）
- [x] 2.9 红态确认：`git stash push -- src/core/ui/repl.py` ⇒ 新增用例**全红**；`git stash pop` 复原

## 3. 实现（绿）

- [x] 3.1 `repl.py` 模块级：`_STEP_TAIL_LINES` / `_MAX_TARGET_CHARS` / `_TARGET_FIELDS` / `_tool_target`
- [x] 3.2 `build_app` 内新增 `_StepBlock(Collapsible)`：`_lines` / `_full` / `_render()` / `feed()` /
       `set_text()` / `on_click()`
- [x] 3.3 `ReplApp.CSS` 新增 `.step-body { color: $text-muted; width: 1fr; }` 与
       `.step-more { color: $text-disabled; width: 1fr; }`
- [x] 3.4 `ReplApp.__init__`：`_actions` 值 → `(box, target)`；`_reasoning` → `_StepBlock | None`
- [x] 3.5 `_add_action_widget`：建 `_StepBlock`（标题带目标）；`completed` 改标题 + `set_text(output)`
- [x] 3.6 `_add_reasoning_widget`：建 `_StepBlock("▸ 思考")`；增量走 `feed()`
- [x] 3.7 绿态确认：`.venv/bin/pytest -q tests/test_repl.py tests/test_ui.py` ⇒ 全绿

## 4. 文档

- [x] 4.1 `doc/03-interfaces/ui-interface.md` §2 补段（步骤块三态 + 目标摘要口径）
- [x] 4.2 `doc/04-testing/test-cases.md` 新节 `## 82.`（TC-STEP-BLOCK，约 8 用例，格式同 §81）
- [x] 4.3 `coding-plan/known-risk.md`：§1 新行 **E106** + §3 ADR-0160 局限行

## 5. 门禁与收口

- [x] 5.1 `ruff check` / `ruff format --check` / `pyright`（0/0/0）/ `pytest -q` 四门禁直连全绿
- [x] 5.2 `openspec validate 2026-10-08-0169-…` ⇒ valid ⇒ 手工归档（**MODIFIED** ⇒ 替换 canonical 中
       该 Requirement，**非**追加；**ADDED** ⇒ 追加末尾；`mkdir -p` 先建目标再 `mv`）⇒
       `openspec validate --all` ⇒ **31/0**
- [x] 5.3 台账回填 + 记忆更新 + **单次提交**
