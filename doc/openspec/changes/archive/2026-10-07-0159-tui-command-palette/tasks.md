# 0159 · 任务清单（TUI 斜杠命令浮层与补全）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`ui` **MODIFIED**「CLI 友好交互」（单一真源命令清单 + `/` 浮层 + 键盘采纳 + 二级枚举参数
> + 审批期不呈现 + 幽灵补全；新增 6 Scenario，既有 7 Scenario 措辞逐字不改）。
> 状态：**已闭**（四门禁全绿；`openspec validate --all` 归档后 30/0）。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/ui/spec.md`（delta，MODIFIED）：补命令浮层/补全/单一真源 + 6 Scenario；`openspec validate` 单条 ⇒ valid
- [x] 1.2 ADR-0151（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 纯函数直测（无 Textual）：`_palette_options` 一级/前缀收窄/未知前缀收起/二级枚举/带空格收起
- [x] 2.2 TUI 红态：`/` 后浮层**存在且可见**、候选含既有 5 命令（实现前无浮层 ⇒ 必红）
- [x] 2.3 TUI 键盘：`↑`/`↓` 移动高亮（焦点仍在输入框）、`Tab` 采纳（只在输入框）、`Esc` 收起
- [x] 2.4 TUI 采纳不提交：浮层打开时 `Enter`（前缀）只改写输入框，`RecordingLoop.inputs` 不增长
- [x] 2.5 TUI 幽灵补全：`/re` ⇒ `Input._suggestion == "/recall"`；`→` 采纳
- [x] 2.6 **守护**：真源内每条命令均可由分发链执行（驱动各自规范形态 ⇒ `loop.inputs` 不增）
- [x] 2.7 **零回归**：既有 10 个斜杠命令用例逐字不动且全绿（`/task*`、`/focus*`、`/summon*`、审批 y/n）
- [x] 2.8 红态确认：以上新用例在实现前**必红**

## 3. 实现

- [x] 3.1 `src/core/ui/repl.py`：模块级 `_Command` / `_COMMANDS` / `_Candidate` / `_palette_options`
- [x] 3.2 `ReplApp`：`#palette`（`OptionList` 子类 `can_focus=False`）+ `CSS` 规则 + `compose`
- [x] 3.3 `_refresh_palette` / `_close_palette` / `_accept_palette_selection` / `on_input_changed`
- [x] 3.4 `on_key`（仅浮层呈现时接管 `↑`/`↓`/`Tab`/`Esc`；`Enter` 显式放行）
- [x] 3.5 `on_input_submitted` 插入采纳分支（审批分支**之后**、`text = …` **之前**）
- [x] 3.6 `Input(suggester=…)` 幽灵补全（与浮层候选同源；`use_cache=False` / `case_sensitive=True`）
- [x] 3.7 `_ask_approval` 主动收起浮层（审批期不遮蔽 y/n）

## 4. 文档同步

- [x] 4.1 `doc/03-interfaces/ui-interface.md` §2：补斜杠命令浮层与补全口径
- [x] 4.2 `doc/04-testing/test-cases.md`：新增 `## 74.`（TC-CMDPAL）
- [x] 4.3 `coding-plan/known-risk.md` §3：加 ADR-0151 局限行

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 全绿（含本 change 新增用例）
- [x] 5.5 `openspec validate --all` ⇒ 归档前 **31/0** ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical（ui）⇒ 移至 `archive/2026-10-07-0159-tui-command-palette/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md` §3；ADR-0151 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`feat(ui): TUI 斜杠命令浮层与补全，命令清单收敛为单一真源（change 0159）`
